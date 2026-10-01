"""One continuous, constrained llama.cpp JSON translation stream."""
import argparse
import codecs
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))

from llama_dll import DirectLlama
from translate import (SYSTEM, TOKEN, JSON_STRING_GRAMMAR, compact,
                       copy_without_translation, en_spans, write_bytes, write_json)

ROOT = Path(__file__).resolve().parent
# A token may contain the field's closing quote plus fixed JSON that follows.
# Permit that tail, then verify its bytes against the fixed source span.
STRING_END = JSON_STRING_GRAMMAR
MAX_CONTROL_CORRECTIONS = 3
CACHE_CHECKPOINT_INTERVAL = 100
CACHE_CHECKPOINT_MAX_BYTES = 16 * 1024 ** 3


def valid_saved_english(value, japanese):
    return (isinstance(value, str) and
            (bool(value.strip()) or
             (copy_without_translation(japanese) and value == japanese)) and
            Counter(TOKEN.findall(value)) == Counter(TOKEN.findall(japanese)))


class InitialContextExceeded(ValueError):
    """The initial full-script prompt cannot fit the context."""


class ConsoleOutput:
    """Keep status lines out of a streaming English line."""

    def __init__(self, stdout=None, stderr=None, color=None):
        self.stdout = stdout if stdout is not None else sys.stdout
        self.stderr = stderr if stderr is not None else sys.stderr
        self.lock = threading.Lock()
        self.english_open = False
        self.pending_status = []
        self.color = self._enable_status_color() if color is None else color

    def _enable_status_color(self):
        if not self.stderr.isatty():
            return False
        if sys.platform != "win32":
            return True
        import ctypes
        import msvcrt
        kernel32 = ctypes.windll.kernel32
        kernel32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        handle = msvcrt.get_osfhandle(self.stderr.fileno())
        mode = ctypes.c_uint32()
        return bool(kernel32.GetConsoleMode(handle, ctypes.byref(mode)) and
                    kernel32.SetConsoleMode(handle, mode.value | 0x0004))

    def line(self, message, stream=None):
        with self.lock:
            target = stream if stream is not None else self.stdout
            target.write(str(message) + "\n")
            target.flush()

    def _write_status(self, message):
        rendered = f"\x1b[90m{message}\x1b[0m" if self.color else message
        self.stderr.write(rendered + "\n")
        self.stderr.flush()

    def status(self, message, heartbeat=False):
        with self.lock:
            if self.english_open:
                if heartbeat and self.pending_status and self.pending_status[-1][1]:
                    self.pending_status[-1] = (message, heartbeat)
                else:
                    self.pending_status.append((message, heartbeat))
                return
            self._write_status(message)

    def begin_english(self, prefix, context_lines=()):
        with self.lock:
            if self.english_open:
                raise RuntimeError("an English line is already open")
            self.english_open = True
            for line in context_lines:
                self.stdout.write(line + "\n")
            self.stdout.write(prefix)
            self.stdout.flush()

    def append_english(self, piece):
        if not piece:
            return
        with self.lock:
            if not self.english_open:
                raise RuntimeError("no English line is open")
            self.stdout.write(piece)
            self.stdout.flush()

    def end_english(self, suffix):
        with self.lock:
            if not self.english_open:
                raise RuntimeError("no English line is open")
            self.stdout.write(suffix + "\n")
            self.stdout.flush()
            self.english_open = False
            for message, _ in self.pending_status:
                self._write_status(message)
            self.pending_status.clear()


CONSOLE = ConsoleOutput()


class StageStatus:
    """Periodic console heartbeat even while a native llama.cpp call blocks."""

    def __init__(self, interval=10, console=None):
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.console = console if console is not None else CONSOLE
        self.stop = threading.Event()
        self.stage = None
        self.interval = interval
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()

    def start(self, name, unit=None, announce=True):
        with self.lock:
            self.stage = name
            self.stage_started = time.monotonic()
            self.cpu_started = time.process_time()
            self.last_progress = self.stage_started
            self.last_report = self.stage_started
            self.done = 0 if unit else None
            self.total = None
            self.unit = unit
            self.announce = announce
        if announce:
            self.console.status(f"[stage] {name}")

    def update(self, done, total=None):
        with self.lock:
            if self.stage is None:
                return
            if self.done != done:
                self.last_progress = time.monotonic()
            self.done = done
            if total is not None:
                self.total = total

    def _snapshot(self):
        with self.lock:
            if self.stage is None:
                return None
            name, started, cpu_started = self.stage, self.stage_started, self.cpu_started
            done, total, unit = self.done, self.total, self.unit
            idle = time.monotonic() - self.last_progress
            announce = self.announce
        elapsed = max(time.monotonic() - started, 0.001)
        cpu = (time.process_time() - cpu_started) / elapsed / max(os.cpu_count() or 1, 1) * 100
        parts = [f"{name}: {elapsed:.0f}s", f"translator CPU {cpu:.0f}%"]
        if done is not None:
            progress = f"{done:,}"
            if total is not None:
                progress += f"/{total:,}"
            parts.append(f"{progress} {unit}")
            if done:
                parts.append(f"{done / elapsed:.1f} {unit}/s")
            if idle >= self.interval:
                parts.append(f"no token progress for {idle:.0f}s")
        return "; ".join(parts), elapsed, announce, name

    def finish(self):
        snapshot = self._snapshot()
        with self.lock:
            self.stage = None
        if snapshot and (snapshot[2] or snapshot[1] >= self.interval):
            self.console.status(f"[stage done] {snapshot[0]}")

    def _heartbeat(self):
        while not self.stop.wait(1):
            snapshot = self._snapshot()
            if not snapshot or snapshot[1] < self.interval:
                continue
            with self.lock:
                now = time.monotonic()
                if self.stage != snapshot[3] or now - self.last_report < self.interval:
                    continue
                self.last_report = now
            total = time.monotonic() - self.started
            self.console.status(f"[still working] {snapshot[0]}; run {total:.0f}s",
                                heartbeat=True)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=1)


def fit_gpu_settings(model_path, context_tokens):
    """Use llama.cpp's own fit command for this model and context."""
    tool = ROOT / "runtime" / "llama" / "llama-fit-params.exe"
    command = [str(tool), "-m", str(model_path), "-c", str(context_tokens),
               "-fitc", str(context_tokens), "-ctk", "q8_0", "-ctv", "q8_0",
               "-nkvo", "-fa", "on", "-b", "2048", "-ub", "512"]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("llama-fit-params failed: " + result.stderr[-2000:])
    args = shlex.split(result.stdout)
    try:
        fitted_context = int(args[args.index("-c") + 1])
        layers = int(args[args.index("-ngl") + 1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError(f"unrecognized llama-fit-params output: {result.stdout!r}") from exc
    if fitted_context != context_tokens:
        raise RuntimeError(f"GPU fit reduced context to {fitted_context}; whole-file stream needs "
                           f"the requested {context_tokens}")
    overrides = []
    if "-ot" in args:
        raw_overrides = args[args.index("-ot") + 1]
        for item in raw_overrides.split(","):
            pattern, buffer_type = item.rsplit("=", 1)
            if buffer_type != "CPU":
                raise RuntimeError(f"unsupported fitted tensor buffer: {buffer_type}")
            overrides.append(pattern)
    if len(args) != 4 + (2 if overrides else 0):
        raise RuntimeError(f"unhandled llama-fit-params arguments: {result.stdout!r}")
    CONSOLE.line(f"llama.cpp GPU fit: {layers} layers, {len(overrides)} CPU tensor overrides "
                 f"at {fitted_context} context")
    return layers, overrides


def payload(doc, english=None, blank_english=False):
    english = english or {}
    return {"game": doc.get("game", ""), "strings": [
        {"id": row["id"], "jp": row["jp"],
         "en": "" if blank_english else row["en"] or english.get(row["id"], "")}
        for row in doc["strings"]]}


def compressed_payload(doc):
    return {"game": doc.get("game", ""), "strings": [
        {"id": row["id"], "jp": row["jp"]}
        for row in doc["strings"]]}


def id_output_template(entries, english=None):
    """Build a compact id-to-English JSON object and locate its value strings."""
    english = english or {}
    parts, spans, cursor = ["{"], [], 1
    for index, row in enumerate(entries):
        if index:
            parts.append(",")
            cursor += 1
        key = compact(row["id"]) + ":"
        parts.append(key)
        cursor += len(key)
        value = compact(row["en"] or english.get(row["id"], ""))
        spans.append((cursor, cursor + len(value)))
        parts.append(value)
        cursor += len(value)
    parts.append("}")
    return "".join(parts), spans


def field_context(index, count, row):
    label = f"[{index}/{count}] {row['id']}"
    return f"{label} jp: {json.dumps(row['jp'], ensure_ascii=False)}"


def sample_field(model, max_field_tokens, progress, console, stage, prefix, row_context):
    if progress:
        progress.start(stage, unit="tokens")
    decoder = codecs.getincrementaldecoder("utf-8")()

    def show_piece(piece):
        console.append_english(decoder.decode(piece))

    console.begin_english(prefix, context_lines=(row_context,))
    try:
        value, tail = model.sample_json_string(
            STRING_END, max_field_tokens, on_piece=show_piece,
            on_token=progress.update if progress else None)
        console.end_english(decoder.decode(b"", final=True) + '"')
        return value, tail
    except BaseException:
        if console.english_open:
            console.end_english(" [interrupted]")
        raise
    finally:
        if progress:
            progress.finish()


def show_existing(index, count, row, english):
    source = "existing" if row["en"] else "checkpoint"
    value = json.dumps(row["en"] or english[row["id"]], ensure_ascii=False)
    CONSOLE.line(field_context(index, count, row) + "\n" +
                 f"[{index}/{count}] {row['id']} [{source}]: {value}")
    return value


def splice_candidate(raw, doc, english):
    source = raw.decode("utf-8-sig")
    spans = en_spans(source)
    if len(spans) != len(doc["strings"]):
        raise ValueError("source en positions differ from parsed strings")
    parts, cursor = [], 0
    for row, (start, end) in zip(doc["strings"], spans):
        parts.extend((source[cursor:start],
                      json.dumps(english.get(row["id"], row["en"]), ensure_ascii=False)))
        cursor = end
    parts.append(source[cursor:])
    result = "".join(parts)
    candidate = json.loads(result)
    for old, new in zip(doc["strings"], candidate["strings"]):
        if {k: v for k, v in old.items() if k != "en"} != {
                k: v for k, v in new.items() if k != "en"}:
            raise ValueError(f"non-English source data changed at {old['id']}")
    return (b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + result.encode("utf-8")


def source_shape_hash(raw):
    """Hash the source bytes with English values blanked, preserving everything else."""
    source = raw.decode("utf-8-sig")
    parts, cursor = [], 0
    for start, end in en_spans(source):
        parts.extend((source[cursor:start], '""'))
        cursor = end
    parts.append(source[cursor:])
    normalized = "".join(parts).encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf"):
        normalized = b"\xef\xbb\xbf" + normalized
    return hashlib.sha256(normalized).hexdigest()


def checkpoint_matches_source(saved, raw, model_tag):
    if saved.get("model_tag") != model_tag:
        return False
    shape = saved.get("source_shape_sha256")
    if shape is not None:
        return shape == source_shape_hash(raw)
    return saved.get("source_sha256") == hashlib.sha256(raw).hexdigest()


def restore_checkpoint_to_source(source_path, checkpoint, model_tag):
    """Apply saved fields to the source before loading the model."""
    raw = source_path.read_bytes()
    doc = json.loads(raw.decode("utf-8-sig"))
    if not checkpoint.exists():
        return doc, raw
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    if not checkpoint_matches_source(saved, raw, model_tag):
        raise ValueError("checkpoint belongs to another source or model")
    english = saved.get("english", {})
    ids = [row["id"] for row in doc["strings"]]
    if len(ids) != len(set(ids)) or set(english) - set(ids):
        raise ValueError("duplicate or unknown source IDs")
    for row in doc["strings"]:
        value = english.get(row["id"])
        if value is None:
            continue
        if not valid_saved_english(value, row["jp"]):
            raise ValueError(f"invalid saved English at {row['id']}")
        if row["en"] and row["en"] != value:
            raise ValueError(f"source English conflicts with checkpoint at {row['id']}")
    if "source_shape_sha256" not in saved:
        saved["source_shape_sha256"] = source_shape_hash(raw)
        write_json(checkpoint, saved)
    if any(not row["en"] and row["id"] in english for row in doc["strings"]):
        write_bytes(source_path, splice_candidate(raw, doc, english))
        CONSOLE.line(f"Restored {len(english)} saved fields into {source_path}")
        raw = source_path.read_bytes()
        doc = json.loads(raw.decode("utf-8-sig"))
    return doc, raw


def export_checkpoint_candidate(raw, doc, checkpoint, model_tag, output):
    """Write a readable partial script from completed checkpoint fields."""
    if not checkpoint.exists():
        return None
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    if not checkpoint_matches_source(saved, raw, model_tag):
        raise ValueError("checkpoint belongs to another source or model")
    english = saved.get("english", {})
    ids = [row["id"] for row in doc["strings"]]
    if len(ids) != len(set(ids)) or set(english) - set(ids):
        raise ValueError("duplicate or unknown source IDs")
    source_rows = {row["id"]: row for row in doc["strings"]}
    if any(not valid_saved_english(value, source_rows[key]["jp"])
           for key, value in english.items()):
        raise ValueError("checkpoint contains invalid English")
    if not english:
        return None
    partial = partial_output_path(output)
    write_bytes(partial, splice_candidate(raw, doc, english))
    CONSOLE.line(f"Saved {len(english)}/{len(ids)} completed fields: {partial}")
    return partial


def partial_output_path(output):
    return output.with_name(output.stem + ".partial" + output.suffix)


def translate_stream(model, doc, raw, checkpoint, model_tag, max_field_tokens,
                     output, source_path, limit=0, progress=None, compress=0):
    if progress:
        progress.start("validating source and checkpoint")
    source_hash = hashlib.sha256(raw).hexdigest()
    shape_hash = source_shape_hash(raw)
    saved = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    if saved and not checkpoint_matches_source(saved, raw, model_tag):
        raise ValueError("checkpoint belongs to another source or model")
    english = saved.get("english", {})
    entries = doc["strings"]
    ids = [row["id"] for row in entries]
    if len(ids) != len(set(ids)) or set(english) - set(ids):
        raise ValueError("duplicate or unknown source IDs")
    for row in entries:
        if not all(isinstance(row.get(key), str) for key in ("id", "jp", "en")):
            raise ValueError("every string needs id, jp, and en text")
        if row["en"] and Counter(TOKEN.findall(row["en"])) != Counter(TOKEN.findall(row["jp"])):
            raise ValueError(f"existing English has runtime token mismatch at {row['id']}")
    untranslated = [row for row in entries if not row["en"]]
    for row in untranslated:
        if row["id"] in english:
            value = english[row["id"]]
            if not valid_saved_english(value, row["jp"]):
                raise ValueError(f"invalid saved English at {row['id']}")
    copied = {row["id"]: row["jp"] for row in untranslated
              if row["id"] not in english and copy_without_translation(row["jp"])}
    if copied:
        english.update(copied)
        candidate = splice_candidate(raw, doc, english)
        write_bytes(source_path, candidate)
        write_json(checkpoint, {"source_sha256": source_hash,
                                "source_shape_sha256": shape_hash,
                                "model_tag": model_tag, "english": english,
                                "next_compress": compress})
        write_bytes(partial_output_path(output), candidate)
        CONSOLE.line(f"Copied {len(copied)} non-linguistic field(s) without translation.")
    pending = [row for row in untranslated if row["id"] not in english]
    if not pending:
        if progress:
            progress.finish()
            progress.start("writing candidate from existing English and checkpoint")
        for index, row in enumerate(entries, 1):
            show_existing(index, len(entries), row, english)
        write_bytes(output, splice_candidate(raw, doc, english))
        if progress:
            progress.finish()
        CONSOLE.line(f"0 pending; candidate: {output}")
        return
    if progress:
        progress.finish()
        progress.start("building and tokenizing full-script prompt")
    stream_entries = [row for row in entries if not copy_without_translation(row["jp"])]
    stream_doc = {"game": doc.get("game", ""), "strings": stream_entries}
    if compress:
        source_payload = compact(compressed_payload(stream_doc))
        output_template, spans = id_output_template(stream_entries, english)
        instruction = ("You will be given the script's text-bearing Japanese rows as ordered JSON. "
                       "Return a JSON object mapping each message id to its English translation. "
                       "The harness supplies every id, quote, colon, comma, and brace and generates "
                       "only one English JSON string value at a time. Preserve character names, "
                       "voice, Japanese meaning, line breaks, and runtime tokens including "
                       "%001 and {X1}. Earlier English "
                       "values in the output are style and terminology references. Return only JSON."
                       "\nJapanese JSON:\n" + source_payload)
    else:
        source_payload = compact(payload(stream_doc, blank_english=True))
        output_template = compact(payload(stream_doc, english))
        spans = en_spans(output_template)
        instruction = ("You will be given untranslated JSON. Return the same JSON with the English "
                       "en fields filled in. The harness supplies every byte outside en and generates "
                       "only one en JSON string at a time. Preserve character names, voice, Japanese "
                       "meaning, line breaks, and runtime tokens including %001 and {X1}. "
                       "Existing English is a style reference. "
                       "Return only JSON.\nUntranslated JSON:\n" + source_payload)
    if len(spans) != len(stream_entries):
        raise ValueError("output value positions differ from parsed strings")
    prefix = model.chat_prompt(SYSTEM, instruction)
    first_pending = next(index for index, row in enumerate(stream_entries)
                         if not row["en"] and row["id"] not in english)
    # Everything through the first pending opening quote is known already.
    # Prefill it as one tokenized sequence rather than replaying saved fields
    # in a second call.
    initial_text = prefix + output_template[:spans[first_pending][0] + 1]
    initial_tokens = len(model.tokenize(initial_text, add_special=True))
    if initial_tokens >= model.context_tokens:
        raise InitialContextExceeded(
            f"initial full-script prompt needs {initial_tokens:,} tokens; "
            f"context is {model.context_tokens:,}")
    CONSOLE.line(f"{len(entries)} rows; {len(stream_entries)} model rows; "
                 f"{len(pending)} pending; initial prompt "
                 f"{initial_tokens:,} tokens; context {model.context_tokens:,}")
    if progress:
        progress.finish()
    if progress:
        progress.start("clearing previous file context")
    model.reset()
    if progress:
        progress.finish()
        progress.start("prefilling initial prompt on model", unit="tokens")
    model.prefill(initial_text, initial=True,
                  on_progress=progress.update if progress else None)
    if progress:
        progress.finish()
    rendered = output_template[:spans[first_pending][0] + 1]
    generated_count = 0
    cache_snapshot_count = 0
    cache_snapshot_seconds = 0.0
    cache_snapshot = None
    cache_snapshot_rendered = None
    forced_parts = []
    positions = {row["id"]: index + 1 for index, row in enumerate(entries)}
    for index, (row, (start, end)) in enumerate(zip(stream_entries, spans)):
        key = row["id"]
        ordinal = positions[key]
        if index < first_pending:
            show_existing(ordinal, len(entries), row, english)
            continue
        if row["en"] or key in english:
            value = show_existing(ordinal, len(entries), row, english)
            forced_parts.append(value[1:])
            rendered += value[1:]
            tail = b""
        else:
            if forced_parts:
                if progress:
                    progress.start(f"prefilling forced JSON before field {ordinal}/{len(entries)} {key}",
                                   unit="tokens", announce=False)
                model.prefill("".join(forced_parts),
                              on_progress=progress.update if progress else None)
                if progress:
                    progress.finish()
                forced_parts.clear()
            console = progress.console if progress else CONSOLE
            row_context = field_context(ordinal, len(entries), row)
            expected_tokens = Counter(TOKEN.findall(row["jp"]))
            if generated_count % CACHE_CHECKPOINT_INTERVAL == 0:
                if cache_snapshot is not None:
                    cache_snapshot.close()
                    cache_snapshot = None
                disk_free = shutil.disk_usage(checkpoint.parent).free
                disk_limit = min(CACHE_CHECKPOINT_MAX_BYTES,
                                 max(0, disk_free - 8 * 1024 ** 3))
                if disk_limit:
                    if progress:
                        progress.start(f"field {key}: saving disk cache checkpoint",
                                       announce=False)
                    snapshot_started = time.monotonic()
                    try:
                        cache_snapshot = model.snapshot_to_disk(checkpoint.parent, disk_limit)
                    except (OSError, RuntimeError, ValueError, MemoryError) as exc:
                        CONSOLE.status(f"Cache checkpoint unavailable at {key}: {exc}")
                    else:
                        cache_snapshot_rendered = rendered
                        snapshot_elapsed = time.monotonic() - snapshot_started
                        cache_snapshot_count += 1
                        cache_snapshot_seconds += snapshot_elapsed
                        CONSOLE.status(f"Cache checkpoint {cache_snapshot_count}: "
                                       f"{cache_snapshot.size / 1073741824:.2f} GiB "
                                       f"temporary disk, {snapshot_elapsed:.2f}s")
                    finally:
                        if progress:
                            progress.finish()
            field_start_tokens = model.tokens_used
            value, tail = sample_field(
                model, max_field_tokens, progress, console,
                f"field {ordinal}/{len(entries)} {key}: generating English",
                f'[{ordinal}/{len(entries)}] {key} [generating]: "', row_context)
            translated = json.loads(value)
            if not isinstance(translated, str) or not translated.strip():
                raise ValueError(f"empty English at {key}")
            corrections = 0
            while (actual_tokens := Counter(TOKEN.findall(translated))) != expected_tokens:
                missing = sorted((expected_tokens - actual_tokens).elements())
                extra = sorted((actual_tokens - expected_tokens).elements())
                if corrections == MAX_CONTROL_CORRECTIONS:
                    raise ValueError(f"runtime token mismatch at {key} after "
                                     f"{corrections} correction(s): missing {missing}, "
                                     f"extra {extra}; {translated!r}")
                corrections += 1
                CONSOLE.line(f"Rejected {key}: missing {missing}, extra {extra}; "
                             f"requesting correction {corrections}/{MAX_CONTROL_CORRECTIONS}")
                correction_prompt = (
                    f"\n##ERROR: Runtime control tokens in field {key} do not match the Japanese.\n"
                    f"Japanese JSON string: {compact(row['jp'])}\n"
                    f"Incorrect English JSON string: {value}\n"
                    f"Required control tokens, including repetitions: "
                    f"{compact(sorted(expected_tokens.elements()))}\n"
                    f"Missing: {compact(missing)}; extra: {compact(extra)}.\n"
                    "Correct this field only. Preserve the Japanese meaning and include every "
                    "required control token exactly once per listed occurrence. "
                    "Return only the corrected English JSON string.\n"
                    "##CORRECTED_ENGLISH_JSON_STRING: \""
                )
                if progress:
                    progress.start(f"field {key}: prefilling correction instructions",
                                   unit="tokens", announce=False)
                model.prefill(correction_prompt,
                              on_progress=progress.update if progress else None)
                if progress:
                    progress.finish()
                value, tail = sample_field(
                    model, max_field_tokens, progress, console,
                    f"field {ordinal}/{len(entries)} {key}: correction "
                    f"{corrections}/{MAX_CONTROL_CORRECTIONS}",
                    f'[{ordinal}/{len(entries)}] {key} '
                    f'[correction {corrections}/{MAX_CONTROL_CORRECTIONS}]: "',
                    row_context)
                translated = json.loads(value)
                if not isinstance(translated, str) or not translated.strip():
                    raise ValueError(f"empty English in correction {corrections} at {key}")
            if corrections:
                if progress:
                    progress.start(f"field {key}: replacing diagnostic branch", announce=False)
                try:
                    model.rewind(field_start_tokens)
                except RuntimeError:
                    if cache_snapshot is not None:
                        model.restore(cache_snapshot)
                        model.prefill(rendered[len(cache_snapshot_rendered):] + value[1:])
                    else:
                        CONSOLE.status("No disk cache checkpoint; replaying full prompt "
                                       "to remove correction instructions")
                        model.reset()
                        model.prefill(prefix + rendered + value[1:], initial=True)
                else:
                    model.prefill(value[1:])
                tail = b""
                if progress:
                    progress.finish()
                CONSOLE.line(f"Accepted {key} after {corrections} correction(s); "
                             "temporary instructions removed.")
            english[key] = translated
            rendered += value[1:]
            generated_count += 1
            if progress:
                progress.start(f"field {key}: saving source and checkpoint", announce=False)
            candidate = splice_candidate(raw, doc, english)
            write_bytes(source_path, candidate)
            write_json(checkpoint, {"source_sha256": source_hash,
                                    "source_shape_sha256": shape_hash,
                                    "model_tag": model_tag, "english": english,
                                    "next_compress": compress})
            write_bytes(partial_output_path(output), candidate)
            if progress:
                progress.finish()
            CONSOLE.line(f"{generated_count}/{len(pending)} generated: {key}; "
                         f"context {model.tokens_used}/{model.context_tokens}")
        next_start = spans[index + 1][0] + 1 if index + 1 < len(spans) else len(output_template)
        suffix = output_template[end:next_start]
        if not suffix.encode("utf-8").startswith(tail):
            raise ValueError(f"generated token crossed fixed JSON at {key}: {tail!r}")
        rendered += suffix
        remaining = suffix.encode("utf-8")[len(tail):]
        if remaining:
            forced_parts.append(remaining.decode("utf-8"))
        if limit and generated_count >= limit:
            break
    if limit and generated_count >= limit:
        if cache_snapshot is not None:
            cache_snapshot.close()
        if cache_snapshot_count:
            CONSOLE.line(f"Cache checkpoints: {cache_snapshot_count}; "
                         f"{cache_snapshot_seconds / generated_count:.2f}s per generated field")
        CONSOLE.line("stopped at requested field limit; checkpoint is resumable")
        return
    if progress:
        progress.start("validating output and writing candidate")
    finished = json.loads(rendered)
    if compress:
        if not isinstance(finished, dict) or list(finished) != [row["id"] for row in stream_entries]:
            raise ValueError("forced output lost or reordered message ids")
        for row in stream_entries:
            value = finished[row["id"]]
            if not isinstance(value, str) or value != (row["en"] or english[row["id"]]):
                raise ValueError(f"forced output changed English at {row['id']}")
    else:
        if len(finished["strings"]) != len(stream_entries):
            raise ValueError("forced output lost strings")
        for source, result in zip(stream_entries, finished["strings"]):
            if result["id"] != source["id"] or result["jp"] != source["jp"]:
                raise ValueError(f"forced JSON changed source text at {source['id']}")
    write_bytes(output, splice_candidate(raw, doc, english))
    if progress:
        progress.finish()
    if cache_snapshot is not None:
        cache_snapshot.close()
    if cache_snapshot_count:
        CONSOLE.line(f"Cache checkpoints: {cache_snapshot_count}; "
                     f"{cache_snapshot_seconds / generated_count:.2f}s per generated field")
    CONSOLE.line(f"candidate: {output}")


def checkpoint_mode(checkpoint, raw, model_tag):
    if not checkpoint.exists():
        return 0
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    if not checkpoint_matches_source(saved, raw, model_tag):
        return 0  # translate_stream reports the source/model mismatch.
    mode = saved.get("next_compress", 0)
    if mode not in (0, 1, 2):
        raise ValueError(f"invalid checkpoint compression mode: {mode!r}")
    return mode


def context_was_exhausted(error):
    return isinstance(error, InitialContextExceeded) or (
        type(error) is ValueError and str(error) == "llama context is full")


def translate_with_fallback(model, doc, raw, checkpoint, model_tag,
                            max_field_tokens, output, source_path, limit=0, progress=None):
    mode = checkpoint_mode(checkpoint, raw, model_tag)
    while mode < 2:
        CONSOLE.line(f"Compression mode {mode}: {len(doc['strings'])} rows")
        try:
            return translate_stream(model, doc, raw, checkpoint, model_tag,
                                    max_field_tokens, output, source_path, limit,
                                    progress=progress, compress=mode)
        except ValueError as exc:
            if not context_was_exhausted(exc):
                raise
            mode += 1
            saved = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {
                "source_sha256": hashlib.sha256(raw).hexdigest(),
                "model_tag": model_tag, "english": {}}
            saved["source_shape_sha256"] = source_shape_hash(raw)
            saved["next_compress"] = mode
            write_json(checkpoint, saved)
            CONSOLE.line(f"Context exhausted; saved English and advancing to compression mode {mode}")
    raise NotImplementedError(f"compression mode 2 is not designed; checkpoint saved at {checkpoint}")


def batch_inputs_from_env():
    count = int(os.environ.get("TRANSLATE_DROP_COUNT", "0"))
    if count < 1:
        raise ValueError("no dropped paths were supplied")
    files, seen, errors = [], set(), 0
    for index in range(1, count + 1):
        value = os.environ.get(f"TRANSLATE_DROP_{index}")
        if not value:
            CONSOLE.line(f"missing dropped path {index}", stream=sys.stderr)
            errors += 1
            continue
        source = Path(value)
        if source.is_dir():
            found = []
            for directory, directories, names in os.walk(source):
                directories.sort(key=str.casefold)
                found.extend(Path(directory) / name for name in sorted(names, key=str.casefold)
                             if name.casefold() == "strings.json")
            if not found:
                CONSOLE.line(f"no strings.json files under {source}", stream=sys.stderr)
                errors += 1
            candidates = ((path, True) for path in found)
        elif source.is_file():
            candidates = ((source, False),)
        else:
            CONSOLE.line(f"path not found: {source}", stream=sys.stderr)
            errors += 1
            continue
        for path, from_folder in candidates:
            key = os.path.normcase(str(path.resolve()))
            if key not in seen:
                seen.add(key)
                files.append((path, from_folder))
    return files, errors


def sort_inputs_by_tokens(model, inputs):
    ranked, errors = [], 0
    for path, from_folder in inputs:
        try:
            raw = path.read_bytes()
            count = len(model.tokenize(raw.decode("utf-8-sig")))
        except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
            CONSOLE.line(f"Could not count tokens for {path}: {exc}", stream=sys.stderr)
            errors += 1
            continue
        ranked.append((count, path, from_folder))
    ranked.sort(key=lambda item: (item[0], str(item[1]).casefold()))
    for index, (count, path, _) in enumerate(ranked, 1):
        CONSOLE.line(f"Queue {index}/{len(ranked)}: {count:,} tokens: {path}")
    return [(path, from_folder) for _, path, from_folder in ranked], errors


def work_for_input(path, model_tag, from_folder):
    default = ROOT / "work" / path.parent.name / model_tag
    if not from_folder:
        return default
    game_root = ROOT.parent / "games"
    if (path.name.casefold() == "strings.json" and
            os.path.normcase(str(path.parent.parent.resolve())) ==
            os.path.normcase(str(game_root.resolve()))):
        return default
    # External folders can share a name. Keep their checkpoints separate.
    identity = os.path.normcase(str(path.resolve())).encode("utf-8")
    suffix = hashlib.sha256(identity).hexdigest()[:12]
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", path.parent.name)
    return ROOT / "work" / f"{safe_name}-{suffix}" / model_tag


def prepare_input(args, input_path, from_folder=False):
    work = args.work or work_for_input(input_path, args.model_tag, from_folder)
    work.mkdir(parents=True, exist_ok=True)
    checkpoint = work / "stream-checkpoint.json"
    output = args.output or work / "strings.translated.json"
    doc, raw = restore_checkpoint_to_source(input_path, checkpoint, args.model_tag)
    return doc, raw, checkpoint, output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("--batch-from-env", action="store_true",
                        help="translate all dropped paths supplied by the batch launcher")
    parser.add_argument("--model", type=Path, default=Path(r"F:\Models") /
                        "DeepSeek-V4-Flash-0731-UD-Q3_K_M-00001-of-00004.gguf")
    parser.add_argument("--model-tag", default="deepseek-v4-flash-q3km")
    parser.add_argument("--context-tokens", type=int, default=262144)
    parser.add_argument("--gpu-layers", type=int, help="override llama.cpp GPU fit")
    parser.add_argument("--threads", type=int, default=4,
                        help="CPU threads for token generation (default: 4)")
    parser.add_argument("--max-field-tokens", type=int, default=3000)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, default=0, help="generate at most N fields")
    parser.add_argument("--recover-only", action="store_true",
                        help="export saved fields without loading the model")
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be at least 1")
    status = StageStatus()
    interrupted = threading.Event()
    previous_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda _number, _frame: interrupted.set())
    try:
        run_pipeline(args, parser, status, interrupted.is_set)
        if interrupted.is_set():
            raise KeyboardInterrupt
    except KeyboardInterrupt:
        CONSOLE.line("Interrupted; completed English fields remain in the checkpoint.",
                     stream=sys.stderr)
        raise SystemExit(130)
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        status.close()


def run_pipeline(args, parser, status, interrupt_requested=lambda: False):
    if args.recover_only:
        if args.batch_from_env or args.input is None:
            parser.error("--recover-only requires one input file")
        doc, raw, checkpoint, output = prepare_input(args, args.input)
        if export_checkpoint_candidate(raw, doc, checkpoint, args.model_tag, output) is None:
            CONSOLE.line(f"No completed fields in checkpoint: {checkpoint}")
        return
    if args.batch_from_env:
        if args.input or args.work or args.output:
            parser.error("batch mode uses dropped paths and separate work folders")
        status.start("scanning dropped folders for strings.json")
        inputs, path_errors = batch_inputs_from_env()
        status.finish()
        CONSOLE.line(f"Queued {len(inputs)} script file(s).")
        if not inputs:
            sys.exit(1)
    else:
        if args.input is None:
            parser.error("an input file is required")
        inputs, path_errors = [(args.input, False)], 0
        CONSOLE.line(f"\nCURRENT SCRIPT: {args.input.resolve()}")
        status.start(f"reading {args.input}")
        prepared = prepare_input(args, args.input)
        status.finish()
    if args.gpu_layers is None:
        status.start("fitting GPU layers and tensor placement in child process")
    gpu_layers, cpu_patterns = ((args.gpu_layers, []) if args.gpu_layers is not None
                                else fit_gpu_settings(args.model, args.context_tokens))
    if interrupt_requested():
        raise KeyboardInterrupt
    if args.gpu_layers is None:
        status.finish()
    else:
        CONSOLE.line(f"Manual GPU layers: {gpu_layers}")
    model = DirectLlama(args.model, args.context_tokens, kv_on_gpu=False,
                        gpu_layers=gpu_layers, cpu_tensor_patterns=cpu_patterns,
                        progress=status, threads=args.threads,
                        interrupt_requested=interrupt_requested)
    status.finish()
    CONSOLE.line(f"Execution: {model.threads} generation CPU threads; "
                 f"{model.batch_threads} prompt/batch CPU threads (llama.cpp default); "
                 f"{gpu_layers} GPU layers; {len(cpu_patterns)} CPU tensor overrides; "
                 "Q8_0 KV cache in system RAM")
    file_failures = 0
    try:
        if args.batch_from_env:
            status.start("counting script tokens and sorting queue")
            inputs, count_errors = sort_inputs_by_tokens(model, inputs)
            path_errors += count_errors
            status.finish()
        for index, (input_path, from_folder) in enumerate(inputs, 1):
            if args.batch_from_env:
                CONSOLE.line(f"\nCURRENT SCRIPT [{index}/{len(inputs)}]: "
                             f"{input_path.resolve()}")
            file_started = time.monotonic()
            try:
                if args.batch_from_env:
                    status.start(f"reading {input_path}", announce=False)
                doc, raw, checkpoint, output = (
                    prepare_input(args, input_path, from_folder)
                    if args.batch_from_env else prepared)
                if args.batch_from_env:
                    status.finish()
                CONSOLE.line(f"Source: {len(raw):,} bytes; {len(doc['strings']):,} rows; "
                             f"checkpoint: {checkpoint}")
                export_checkpoint_candidate(raw, doc, checkpoint, args.model_tag, output)
                completed = False
                try:
                    translate_with_fallback(model, doc, raw, checkpoint, args.model_tag,
                                            args.max_field_tokens, output, input_path, args.limit,
                                            progress=status)
                    completed = True
                finally:
                    if not completed or args.limit:
                        export_checkpoint_candidate(raw, doc, checkpoint,
                                                    args.model_tag, output)
                CONSOLE.line(f"File finished in {time.monotonic() - file_started:.0f}s: "
                             f"{input_path}")
            except Exception as exc:
                if not args.batch_from_env:
                    raise
                file_failures += 1
                CONSOLE.line(f"Failed: {input_path}: {exc}", stream=sys.stderr)
    finally:
        status.start("unloading model and context")
        model.close()
        status.finish()
    if args.batch_from_env:
        errors = path_errors + file_failures
        CONSOLE.line(f"Finished {len(inputs) - file_failures} of {len(inputs)} "
                     f"script file(s); {errors} error(s).")
        if errors:
            sys.exit(1)


if __name__ == "__main__":
    main()
