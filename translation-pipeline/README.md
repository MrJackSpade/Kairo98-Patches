# Local whole-file translation stream

`translate_stream.py` calls the llama.cpp DLL directly through `ctypes`. There is no server. The default model is [Unsloth's DeepSeek V4 Flash 0731 UD-Q3_K_M](https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF/tree/main/UD-Q3_K_M), a four-shard GGUF. Keep all four shards together in `F:\Models` and pass the first shard to llama.cpp. The downloader in `downloads/download_q3.py` verifies each shard against its published SHA-256. The runtime and working directories are gitignored.

## Run one selected game

From the repository root in PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\translation-pipeline\run-stream.ps1 -InputFile .\games\intruder\strings.json -Model deepseek -ContextTokens 262144
```

The runner calls the bundled `llama-fit-params.exe` for the selected model and context, then passes its fitted GPU layer count and CPU tensor placement rules into the DLL. `-GpuLayers` is an optional manual override. The KV cache is Q8_0 in system RAM. Increase `-ContextTokens` only after checking available memory. The runner advances from compression mode 0 to 1 if the initial full-script prompt cannot fit, or if actual generation fills the context. English length is not guessed for the decision.

To stop after a few fields for review, pass `-Limit 5`. Reuse the same arguments to resume from the checkpoint. After every completed field, the runner writes and flushes the updated `en` values directly into the input `strings.json`, then saves the checkpoint and a partial candidate. These writes atomically replace their previous files. If power is lost between writes, the next run reconciles the source and checkpoint before loading the model. An in-progress field must be regenerated. A completed run also writes `strings.translated.json` under `translation-pipeline/work/<game>/<model>/` unless `-Work` or `-Output` is supplied.

To export a checkpoint without loading the model, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\translation-pipeline\run-stream.ps1 -InputFile .\games\intruder\strings.json -Model deepseek -RecoverOnly
```

This restores completed fields into the input `strings.json` and writes `strings.translated.partial.json` next to the checkpoint, without loading the model. It verifies that the checkpoint matches the source apart from its English values.

## Run several selected games

Place one `strings.json` path per line in a UTF-8 file, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\translation-pipeline\run-many-stream.ps1 -FileList .\selected-games.txt -Model deepseek
```

The list should contain only games whose extraction and translation eligibility have been reviewed. The runner counts tokens with the selected model's tokenizer, processes files from shortest to longest, and continues past individual failures while preserving their checkpoints. It loads the model once for the queue.

## Drag-and-drop queue

Drop one or more folders onto `translate-drag-drop.bat` in the repository root. It finds `strings.json` recursively, processes each file in order, and continues past individual failures. Dropping a single file still works. The window stays open after the queue finishes.

To remove translations, drop one or more script files or folders onto `clear-drag-drop.bat`. It uses the same folder scan. For multiple files needing changes, it lists every file and the total, then requires one `CLEAR ALL` confirmation for the batch. A single file still requires `CLEAR`; Enter skips. It clears nonempty `en` fields and archives active translation checkpoints for each script, so the next run starts fresh. A script with empty English but an active checkpoint is still included. Japanese, translator notes, other fields, and formatting are preserved. You can also run `python translation-pipeline/clear_english.py <file-or-folder>` directly with any Python 3 installation.

The queue counts script tokens and runs from shortest to longest. It fits and loads DeepSeek once, then resets its context for each file without unloading the model weights. A prominent `CURRENT SCRIPT` line prints the full `strings.json` path before work begins on each file. Each displayed field then shows its Japanese text immediately before the English line, including existing or checkpointed English. The console streams new English as it is generated and labels scanning, GPU fitting, model loading, context allocation, prompt prefill, and field generation; long stages report elapsed time, translator CPU, and token rate where available. Status lines appear in dark grey in supported terminals and wait until a streaming English line is complete, so they cannot split the text. Short fixed-JSON prefills do not print status lines. A folder run keeps checkpoints for direct `games/<title>/strings.json` files in their usual work directories; other paths get a stable, path-specific work directory to avoid collisions.

Untranslated rows containing only whitespace, punctuation, numbers, mathematical or currency signs, or common decorative marks are copied exactly from `jp` to `en` without entering the model prompt. The copy is saved to the source, checkpoint, and partial candidate, including when resuming an existing run. Any row containing a letter or an unrecognized character still goes to the model.

Generation uses four CPU threads by default (`translate_stream.py --threads` can change this); prompt/batch processing retains llama.cpp's default thread setting. GPU fit controls tensor placement. The console reports the resulting GPU layers and CPU tensor overrides. The Q8_0 KV cache remains in system RAM at this context size.

## Forced JSON behavior

The model uses the [anime-literate English style rules](FANSUB_STYLE.md): it keeps forms of address and familiar Japanese cultural referents while translating ordinary dialogue into fluent English.

The system instruction and a compact JSON file containing only `game`, `id`, `jp`, and `en` are loaded into one llama.cpp context. The harness then starts an output copy of that JSON. On resume, it prefills the full known prefix through the opening quote of the first untranslated `en` value in one call. It lets the model generate only that JSON string, then collects fixed JSON and existing English up to the next field needing generation into one prefill call. Escaped quotes and Unicode escapes are recognized as part of the string. Existing English is forced unchanged. The entire output is one continuous context, so earlier generated translations remain visible to later fields.

Each file starts in compression mode 0, the full JSON stream described above. If its initial prompt cannot fit or actual generation fills the context, the runner saves all completed English values and retries that file in mode 1. Mode 1 sends ordered `game` and `{id,jp}` rows, then builds a JSON output object mapping each `id` to English. The harness still supplies every key and separator and constrains each generated value to one JSON string. English already generated in mode 0 is forced into this output stream, and the usual full `strings.translated.json` candidate is written when all rows finish. If mode 1 also fills the context, the checkpoint records mode 2 as next; mode 2 has no format yet, so that job stops with a clear error. A resumed job starts at the mode recorded in its checkpoint. Other errors do not trigger compression.

After each field, the runner splices completed English values into the source file's exact text and verifies that every non-English field is unchanged. It also saves a checkpoint and partial candidate after each field. Runtime tokens such as `{X1}` are checked. On a token mismatch, the runner keeps the rejected value in a temporary model branch, appends a field-specific `##ERROR` with the missing and extra tokens, and requests up to three corrections. Once one passes, it tries to rewind that branch and feeds the accepted JSON string into the continuing script. For models that cannot partially rewind, it restores a temporary disk cache checkpoint and replays only the fields since that checkpoint. A checkpoint is made before the first pending field and every 100 generated fields thereafter; its size and time are logged. Only one checkpoint is kept per file, it is capped at 16 GiB while leaving at least 8 GiB free, and it is deleted when the file finishes. If a checkpoint cannot be made, correction falls back to replaying the full prompt. If all three corrections fail, the file stops with its prior completed fields preserved. This structural check does not replace review of Japanese meaning, names, consistency, display limits, or translator notes before merging a candidate.

## Comparison

The small neutral `comparison-sample.json` exercises quoted dialogue and runtime tokens. The stream can also run with `-Model qwen` or `-Model gemma` after those models are present. Their full-file context setting must be large enough for the selected script. `translate.py` and `run-translate.ps1` are the earlier batch approach; `translate_stream.py` is the continuous stream requested here.

The DLLs are from llama.cpp release `b11205`; the embedded Python is the official Windows 3.12.10 build. Keep the binding matched to the llama.cpp headers when updating the runtime.

The four DeepSeek shards and GPU fit calculation are verified. A single-field DeepSeek DLL test at 262,144 context passed on the neutral sample. Fit selected 44 GPU layers with 39 CPU tensor overrides; GPU use rose to about 23.0 GB (1.3 GB free), and Windows reported about 35.8 GB available RAM during the run. The test generated only `m001` and stopped with a resumable checkpoint. Full-file throughput and long-context quality remain unmeasured.
