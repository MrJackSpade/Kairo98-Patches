"""Local, resumable Japanese-to-English translation for Kairo98 strings.json files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import unicodedata
sys.path.insert(0, str(Path(__file__).resolve().parent))
from llama_dll import DirectLlama

TOKEN = re.compile(r"\{[A-Z]\d+\}|%(?:\d*\.\d+[A-Za-z]+|\d+[A-Za-z]+|[A-Za-z]+|\d+)")
ROOT = Path(__file__).resolve().parent
DEFAULT_WORK = ROOT / "work"
SYSTEM = (
    "Translate Japanese PC-98 visual novels for English-speaking readers who know anime and "
    "Japanese game culture. Write fluent adult English, preserving meaning, speaker voice, "
    "relationships, humor, explicitness, names, runtime tokens such as {X1}, %001, "
    "and printf placeholders such as %s or %2d, and intentional "
    "line breaks. Use full story context to resolve ambiguous short lines. "
    "Keep Japanese forms of address: name suffixes -san, -chan, -kun, -sama and spoken terms "
    "such as senpai, kohai, and sensei. Keep kinship-style vocatives such as Onee-san, "
    "Onee-chan, Onii-san, and Onii-chan; never replace them with Big Sister or Big Brother. "
    "A confirmed family relationship described in narration may be translated as older sister "
    "or older brother. Preserve changes in names, nicknames, titles, and honorifics; do not "
    "invent or remove them. Keep familiar Japanese cultural referents such as Obon, onsen, "
    "bento, onigiri, kimono, yukata, manga, doujin, otaku, and yen rather than Westernizing "
    "them. Translate ordinary Japanese words into natural English; keep a Japanese word when "
    "it is itself a name, catchphrase, or piece of wordplay. Do not leave random romaji or add "
    "explanatory glosses. Preserve period details and do not invent relationships or "
    "cultural equivalents. Never censor, soften, infantilize, or add cheerful dub-style "
    "catchphrases or modern slang absent from the source. Translate idioms naturally without "
    "changing their point. Do not add translator notes inside en. Return only the requested JSON."
)
JSON_STRING_GRAMMAR = r'''root ::= ([^"\\\x7F\x00-\x1F] | "\\" (["\\bfnrt] | "u" [0-9a-fA-F]{4}))+ "\"" .*'''
DECORATIVE_SYMBOLS = frozenset("♪♫♬♩★☆♥♡")


def copy_without_translation(value):
    """Copy known non-linguistic characters; leave unknowns for MTL."""
    return all(char.isspace() or char in DECORATIVE_SYMBOLS or
               unicodedata.category(char)[0] in "NPZ" or
               unicodedata.category(char) in ("Sm", "Sc", "Sk")
               for char in value)


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def write_json(path, value):
    write_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))


def write_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def estimated_tokens(text):
    # Deliberately conservative without a tokenizer. llama.cpp still enforces the real limit.
    return max(len(text) // 3, len(text.encode("utf-8")) // 2)


def string_end(source, start):
    if source[start] != '"':
        raise ValueError("expected JSON string")
    index = start + 1
    while index < len(source):
        if source[index] == "\\":
            index += 2
        elif source[index] == '"':
            return index + 1
        else:
            index += 1
    raise ValueError("unterminated JSON string")


def en_spans(source):
    """Locate exact quoted values of en keys, respecting escaped quotes."""
    spans = []
    index = 0
    while index < len(source):
        if source[index] != '"':
            index += 1
            continue
        end = string_end(source, index)
        key = json.loads(source[index:end])
        cursor = end
        while cursor < len(source) and source[cursor].isspace():
            cursor += 1
        if key == "en" and cursor < len(source) and source[cursor] == ":":
            cursor += 1
            while cursor < len(source) and source[cursor].isspace():
                cursor += 1
            value_end = string_end(source, cursor)
            spans.append((cursor, value_end))
            index = value_end
        else:
            index = end
    return spans


def force_english_fields(model, messages, batch_json, max_tokens, shared_prefix=None):
    """Prefill literal JSON, let llama.cpp generate only each JSON string value."""
    spans = en_spans(batch_json)
    if not spans:
        raise ValueError("batch has no en fields")
    template = model.chat_prompt(messages[0]["content"], messages[1]["content"])
    if shared_prefix:
        prefix_text, snapshot = shared_prefix
        if not template.startswith(prefix_text):
            raise RuntimeError("batch prompt does not match saved full-script prefix")
        template = template[len(prefix_text):]
    rendered = batch_json[:spans[0][0] + 1]
    if shared_prefix:
        model.restore(snapshot)
        model.prefill(template + rendered)
    else:
        model.reset()
        model.prefill(template + rendered, initial=True)
    for index, (start, end) in enumerate(spans):
        generated, tail = model.sample_json_string(JSON_STRING_GRAMMAR, max_tokens)
        english = json.loads(generated)
        if not isinstance(english, str) or not english.strip():
            raise ValueError(f"empty English JSON string at field {index + 1}")
        next_start = spans[index + 1][0] + 1 if index + 1 < len(spans) else len(batch_json)
        suffix = batch_json[end:next_start]
        rendered += generated[1:] + suffix
        if index + 1 < len(spans):
            if suffix.encode("utf-8").startswith(tail):
                remaining = suffix.encode("utf-8")[len(tail):]
                try:
                    model.prefill(remaining.decode("utf-8"))
                except UnicodeDecodeError:
                    if shared_prefix:
                        model.restore(snapshot)
                        model.prefill(template + rendered)
                    else:
                        model.reset()
                        model.prefill(template + rendered, initial=True)
            else:
                if shared_prefix:
                    model.restore(snapshot)
                    model.prefill(template + rendered)
                else:
                    model.reset()
                    model.prefill(template + rendered, initial=True)
    return json.loads(rendered), rendered


def context_request(model, prompt, max_tokens):
    model.reset()
    template = model.chat_prompt(SYSTEM, prompt + "\nReturn your summary as one nonempty JSON string.")
    model.prefill(template + '"', initial=True)
    result = json.loads(model.sample_json_string(JSON_STRING_GRAMMAR, max_tokens)[0])
    if not isinstance(result, str) or not result.strip():
        raise ValueError("empty model context summary")
    return result


def chunks(entries, max_tokens):
    group = []
    used = 0
    for entry in entries:
        cost = estimated_tokens(compact(entry)) + 20
        if cost > max_tokens:
            raise ValueError(f"entry {entry['id']} exceeds the context chunk budget")
        if group and used + cost > max_tokens:
            yield group
            group, used = [], 0
        group.append(entry)
        used += cost
    if group:
        yield group


def context_entries(doc):
    return [{"id": e["id"], "kind": e.get("kind"), "jp": e["jp"],
             **({"en": e["en"]} if e["en"] else {}),
             **({"tn_note": e["tn_note"]} if e.get("tn_note") else {})}
            for e in doc["strings"] if not copy_without_translation(e["jp"])]


def build_context(doc, source_sha, work, model, context_budget):
    context_path = work / "context.json"
    if context_path.exists():
        existing = json.loads(context_path.read_text(encoding="utf-8"))
        if existing.get("source_sha256") == source_sha and existing.get("global_summary"):
            return existing
    entries = context_entries(doc)
    # Every source line is included in exactly one pass. Store each chunk's notes durably.
    groups = list(chunks(entries, context_budget))
    context = {"source_sha256": source_sha, "game": doc.get("game"), "chunks": []}
    if context_path.exists():
        old = json.loads(context_path.read_text(encoding="utf-8"))
        if old.get("source_sha256") == source_sha:
            context = old
    for index, group in enumerate(groups):
        if index < len(context["chunks"]):
            continue
        previous = context["chunks"][-1]["summary"] if context["chunks"] else ""
        prompt = (
            "Read this ordered portion of a complete Japanese game script. Record characters, "
            "relationships, names, honorifics, chronology, setting, recurring terms, voice, "
            "jokes, and ambiguities relevant to later translation. Keep the record compact and "
            "factual. Treat existing English as a terminology and style reference. Game: " +
            str(doc.get("game", "")) + ". Previous portion's context:\n" + previous[-5000:] +
            "\nCurrent portion:\n" + compact(group)
        )
        summary = context_request(model, prompt, 1500)
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(f"empty context summary at chunk {index + 1}")
        context["chunks"].append({"first_id": group[0]["id"], "last_id": group[-1]["id"],
                                  "summary": summary})
        write_json(context_path, context)
        print(f"context {index + 1}/{len(groups)}", flush=True)
    summaries = [item["summary"] for item in context["chunks"]]
    # Reduce all ordered notes in stages; do not drop the middle of a long game.
    if not context.get("global_summary"):
        while len(summaries) > 1:
            reduced = []
            for start in range(0, len(summaries), 3):
                group = summaries[start:start + 3]
                if len(group) == 1:
                    reduced.append(group[0])
                    continue
                prompt = (
                    "Combine these ordered game notes into a compact, faithful story and "
                    "terminology guide. Preserve character relationships, chronology, names, "
                    "voice, and unresolved ambiguity:\n" + compact(group)
                )
                reduced.append(context_request(model, prompt, 1800))
            summaries = reduced
        context["global_summary"] = summaries[0] if summaries else ""
        write_json(context_path, context)
    return context


def validate(source_entries, response):
    rows = response.get("strings") if isinstance(response, dict) else None
    if not isinstance(rows, list) or len(rows) != len(source_entries):
        raise ValueError("response has missing or extra strings")
    expected = {e["id"]: e for e in source_entries}
    seen = {}
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"id", "en", "tn_note"}:
            raise ValueError("response field mismatch")
        key = row.get("id")
        if key not in expected or key in seen:
            raise ValueError(f"unknown or duplicate id: {key}")
        en = row.get("en")
        if not isinstance(en, str) or not en.strip():
            raise ValueError(f"empty English for {key}")
        if sorted(TOKEN.findall(en)) != sorted(TOKEN.findall(expected[key]["jp"])):
            raise ValueError(f"runtime token mismatch for {key}")
        if "tn_note" in row and not isinstance(row["tn_note"], str):
            raise ValueError(f"bad translator note for {key}")
        seen[key] = row
    return seen


def run(args):
    source = Path(args.input).resolve()
    raw = source.read_bytes()
    doc = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(doc.get("strings"), list) or not all(
        isinstance(e, dict) and isinstance(e.get("id"), str) and
        isinstance(e.get("jp"), str) and isinstance(e.get("en"), str)
        for e in doc["strings"]
    ):
        raise ValueError("expected Kairo98 strings.json with id, jp, en in each string")
    if len({e["id"] for e in doc["strings"]}) != len(doc["strings"]):
        raise ValueError("duplicate source IDs")
    source_sha = hashlib.sha256(raw).hexdigest()
    work = Path(args.work).resolve() if args.work else DEFAULT_WORK / source.parent.name / args.model_tag
    work.mkdir(parents=True, exist_ok=True)
    checkpoint = work / "translations.json"
    saved = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {}
    if saved and (saved.get("source_sha256") != source_sha or saved.get("model_tag") != args.model_tag):
        raise ValueError("source or model changed since checkpoint; use a new --work folder")
    rows = saved.get("strings", {})
    eligible = [e for e in doc["strings"] if args.all or not e["en"]]
    copied = [e for e in eligible if e["id"] not in rows and
              copy_without_translation(e["jp"])]
    for entry in copied:
        rows[entry["id"]] = {"id": entry["id"], "en": entry["jp"]}
    todo = [e for e in eligible if e["id"] not in rows]
    full_prompt_cost = 2 * estimated_tokens(compact(doc)) + args.max_output_tokens + 1500
    mode = "whole" if full_prompt_cost <= args.context_tokens * 0.8 else "context"
    if args.mode == "whole":
        mode = "whole"
    if args.mode == "context":
        mode = "context"
    print(f"{doc.get('game', source.parent.name)}: {len(todo)} pending, "
          f"{len(copied)} copied without translation, mode={mode}", flush=True)
    if args.dry_run:
        return
    if copied:
        write_json(checkpoint, {"source_sha256": source_sha,
                                "model_tag": args.model_tag, "strings": rows})
    if not todo:
        run_loaded(args, doc, raw, source_sha, work, saved, rows, todo, eligible, mode, None)
        return
    model_path = ROOT / "models" / ("gemma-4-31B-it-QAT-Q4_0.gguf" if args.model_tag == "gemma" else "Qwen3.8-27B-Q4_K_M.gguf")
    if not model_path.exists():
        raise ValueError(f"model is missing: {model_path}")
    model = DirectLlama(model_path, args.context_tokens)
    try:
        run_loaded(args, doc, raw, source_sha, work, saved, rows, todo, eligible, mode, model)
    finally:
        model.close()


def run_loaded(args, doc, raw, source_sha, work, saved, rows, todo, eligible, mode, model):
    checkpoint = work / "translations.json"
    context = None
    shared_prefix = None
    system_prompt = SYSTEM
    if mode == "whole" and todo:
        system_prompt += "\nComplete ordered script context:\n" + compact(context_entries(doc))
        marker = "__TRANSLATION_BATCH_START__"
        prefix_text = model.chat_prompt(system_prompt, marker).split(marker, 1)[0]
        model.reset()
        model.prefill(prefix_text, initial=True)
        shared_prefix = (prefix_text, model.snapshot())
        print(f"full-script prefix cached: {model.tokens_used} tokens", flush=True)
    if mode == "context" and todo:
        context = build_context(doc, source_sha, work, model, min(args.context_tokens // 3, 6000))
    all_entries = doc["strings"]
    positions = {e["id"]: i for i, e in enumerate(all_entries)}
    for batch_index, batch in enumerate(chunks(todo, min(args.context_tokens // 5, 3500))):
        # Bound the response length as well as the prompt length.
        for start in range(0, len(batch), args.batch_size):
            target = batch[start:start + args.batch_size]
            target_positions = [positions[e["id"]] for e in target]
            neighborhood_positions = sorted({near
                                             for position in target_positions
                                             for near in range(max(0, position - 3),
                                                               min(len(all_entries), position + 4))})
            neighborhood = [all_entries[position] for position in neighborhood_positions
                            if not copy_without_translation(all_entries[position]["jp"])]
            surrounding = [{"id": e["id"], "jp": e["jp"], "en": e["en"]} for e in neighborhood]
            batch_doc = {"game": doc.get("game"),
                         "strings": [{**e, "en": ""} for e in target]}
            batch_json = compact(batch_doc)
            context_data = {"game": doc.get("game"), "surrounding_strings": surrounding}
            if mode == "context":
                summaries = context["chunks"]
                context_data["game_context"] = context.get("global_summary", "")
                nearby = [s["summary"] for s in summaries
                          if any(positions[s["first_id"]] <= position <= positions[s["last_id"]]
                                 for position in target_positions)]
                context_data["local_context"] = nearby[:2]
            prompt = (
                "You will be given untranslated JSON. Return exactly the same JSON with only "
                "the en string values filled in. The harness supplies every byte outside en, "
                "including quotes and escapes; generate only the next complete JSON string "
                "value when prompted. Do not change ids, Japanese, metadata, or structure. "
                "Keep runtime tokens verbatim. Use literal English when an adaptation would "
                "need a translator note.\nContext:\n" + compact(context_data) +
                "\nUntranslated JSON:\n" + batch_json
            )
            prompt_tokens = len(model.tokenize(model.chat_prompt(system_prompt, prompt) + batch_json))
            prefix_tokens = prompt_tokens
            output_reserve = sum(min(args.max_output_tokens,
                                     max(128, len(model.tokenize(entry["jp"])) * 4))
                                 for entry in target)
            if prefix_tokens + output_reserve + 32 > args.context_tokens:
                raise ValueError(f"batch around {target[0]['id']} needs about "
                                 f"{prefix_tokens + output_reserve + 32} tokens; "
                                 "lower --batch-size or increase --context-tokens")
            response, forced_json = force_english_fields(
                model, [{"role": "system", "content": system_prompt},
                              {"role": "user", "content": prompt}], batch_json,
                args.max_output_tokens, shared_prefix)
            filled = response.get("strings")
            if not isinstance(filled, list) or len(filled) != len(target):
                raise ValueError("forced output changed batch structure")
            for original, produced in zip(target, filled):
                if {k: v for k, v in produced.items() if k != "en"} != {k: v for k, v in original.items() if k != "en"}:
                    raise ValueError(f"forced output changed non-English fields near {original['id']}")
            checked = validate(target, {"strings": [{"id": e["id"], "en": e["en"]} for e in filled]})
            batch_path = work / "batches" / f"batch_{len(rows) + 1:06d}.json"
            batch_path.parent.mkdir(parents=True, exist_ok=True)
            batch_path.write_text(forced_json + "\n", encoding="utf-8")
            rows.update(checked)
            write_json(checkpoint, {"source_sha256": source_sha, "model_tag": args.model_tag, "strings": rows})
            print(f"translated {len(rows)} / {len(eligible)}: {target[0]['id']}..{target[-1]['id']}", flush=True)
    original_text = raw.decode("utf-8-sig")
    spans = en_spans(original_text)
    if len(spans) != len(doc["strings"]):
        raise ValueError("source JSON en positions do not match string entries")
    pieces = []
    cursor = 0
    for entry, (start, end) in zip(doc["strings"], spans):
        pieces.append(original_text[cursor:start])
        if entry["id"] in rows:
            pieces.append(json.dumps(rows[entry["id"]]["en"], ensure_ascii=False))
        else:
            pieces.append(original_text[start:end])
        cursor = end
    pieces.append(original_text[cursor:])
    candidate_text = "".join(pieces)
    candidate = json.loads(candidate_text)
    for before, after in zip(doc["strings"], candidate["strings"]):
        if {k: v for k, v in before.items() if k != "en"} != {k: v for k, v in after.items() if k != "en"}:
            raise ValueError(f"candidate altered non-English fields at {before['id']}")
    output = Path(args.output).resolve() if args.output else work / "strings.translated.json"
    write_bytes(output, (b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + candidate_text.encode("utf-8"))
    print(f"candidate: {output}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="path to a game's strings.json")
    parser.add_argument("--model-tag", default="qwen", help="checkpoint label, e.g. qwen or gemma")
    parser.add_argument("--work", help="checkpoint and context directory")
    parser.add_argument("--output", help="candidate JSON path; source is never changed")
    parser.add_argument("--mode", choices=["auto", "whole", "context"], default="auto")
    parser.add_argument("--context-tokens", type=int, default=16384)
    parser.add_argument("--max-output-tokens", type=int, default=3000)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--all", action="store_true", help="also retranslate existing English")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.batch_size < 1 or args.context_tokens < 4096:
        parser.error("batch-size must be positive and context-tokens at least 4096")
    try:
        run(args)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
