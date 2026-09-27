# Local whole-file translation stream

`translate_stream.py` calls the llama.cpp DLL directly through `ctypes`. There is no server. The default model is [Unsloth's DeepSeek V4 Flash 0731 UD-Q3_K_M](https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF/tree/main/UD-Q3_K_M), a four-shard GGUF. Keep all four shards together in `F:\Models` and pass the first shard to llama.cpp. The downloader in `downloads/download_q3.py` verifies each shard against its published SHA-256. The runtime and working directories are gitignored.

## Run one selected game

From the repository root in PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\translation-pipeline\run-stream.ps1 -InputFile .\games\intruder\strings.json -Model deepseek -ContextTokens 262144
```

The runner calls the bundled `llama-fit-params.exe` for the selected model and context, then passes its fitted GPU layer count and CPU tensor placement rules into the DLL. `-GpuLayers` is an optional manual override. The KV cache is Q8_0 in system RAM. Increase `-ContextTokens` only after checking available memory. The runner computes the actual tokenizer cost and rejects a full-file stream if its minimum output reserve will exceed the configured context. A later field can still exhaust context if English runs longer than that reserve.

To stop after a few fields for review, pass `-Limit 5`. Reuse the same arguments to resume from the checkpoint. The source file is not edited. The candidate and per-field checkpoint appear under `translation-pipeline/work/<game>/<model>/` unless `-Work` or `-Output` is supplied.

## Run several selected games

Place one `strings.json` path per line in a UTF-8 file, then run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\translation-pipeline\run-many-stream.ps1 -FileList .\selected-games.txt -Model deepseek
```

The list should contain only games whose extraction and translation eligibility have been reviewed. The command stops on the first failure and preserves its checkpoint.

## Forced JSON behavior

The system instruction and a compact JSON file containing only `game`, `id`, `jp`, and `en` are loaded into one llama.cpp context. The harness then starts an output copy of that JSON. It prefills every byte through the opening quote of the next `en` value, lets the model generate only that JSON string, and then prefills the fixed bytes through the next `en` opening quote. Escaped quotes and Unicode escapes are recognized as part of the string. Existing English is forced unchanged. The entire output is one continuous context, so earlier generated translations remain visible to later fields.

After the stream, the runner splices English values into the original file's exact text and verifies that every non-English field is unchanged. The checkpoint is saved after every generated field. Runtime tokens such as `{X1}` are checked. This structural check does not replace review of Japanese meaning, names, consistency, display limits, or translator notes before merging a candidate.

## Comparison

The small neutral `comparison-sample.json` exercises quoted dialogue and runtime tokens. The stream can also run with `-Model qwen` or `-Model gemma` after those models are present. Their full-file context setting must be large enough for the selected script. `translate.py` and `run-translate.ps1` are the earlier batch approach; `translate_stream.py` is the continuous stream requested here.

The DLLs are from llama.cpp release `b11205`; the embedded Python is the official Windows 3.12.10 build. Keep the binding matched to the llama.cpp headers when updating the runtime.

The four DeepSeek shards and GPU fit calculation are verified. A single-field DeepSeek DLL test at 262,144 context passed on the neutral sample. Fit selected 44 GPU layers with 39 CPU tensor overrides; GPU use rose to about 23.0 GB (1.3 GB free), and Windows reported about 35.8 GB available RAM during the run. The test generated only `m001` and stopped with a resumable checkpoint. Full-file throughput and long-context quality remain unmeasured.
