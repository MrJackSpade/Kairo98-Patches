"""Clear translated en fields from Kairo98 JSON scripts after confirmation."""

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class ClearPlan:
    path: Path
    from_folder: bool
    source_sha256: bytes
    fields: int
    checkpoints: tuple


def string_end(source, start):
    if start >= len(source) or source[start] != '"':
        raise ValueError("expected a JSON string")
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
    """Find quoted values of en keys without changing surrounding formatting."""
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


def cleared_bytes(raw):
    source = raw.decode("utf-8-sig")
    document = json.loads(source)
    rows = document.get("strings") if isinstance(document, dict) else None
    if not isinstance(rows, list) or not all(
        isinstance(row, dict) and isinstance(row.get("en"), str) for row in rows
    ):
        raise ValueError("expected a Kairo98 script with strings containing en text")
    spans = en_spans(source)
    if len(spans) != len(rows):
        raise ValueError("en field positions do not match script rows")
    parts = []
    cursor = 0
    count = 0
    for row, (start, end) in zip(rows, spans):
        if json.loads(source[start:end]) != row["en"]:
            raise ValueError("en field order does not match script rows")
        if row["en"]:
            parts.extend((source[cursor:start], '""'))
            cursor = end
            count += 1
        row["en"] = ""
    if not count:
        return raw, 0
    parts.append(source[cursor:])
    result = "".join(parts)
    if json.loads(result) != document:
        raise ValueError("cleared script changed fields outside en")
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    return bom + result.encode("utf-8"), count


def dropped_paths():
    count = int(os.environ.get("CLEAR_DROP_COUNT", "0"))
    if count < 1:
        raise ValueError("no dropped paths were supplied")
    return [os.environ.get(f"CLEAR_DROP_{index}", "")
            for index in range(1, count + 1)]


def collect_files(paths):
    files = []
    seen = set()
    errors = 0
    for value in paths:
        path = Path(value) if value else None
        if path is not None and path.is_dir():
            found = []
            for directory, directories, names in os.walk(path):
                directories.sort(key=str.casefold)
                found.extend(Path(directory) / name for name in sorted(names, key=str.casefold)
                             if name.casefold() == "strings.json")
            if not found:
                print(f"No strings.json files under {path}", file=sys.stderr)
                errors += 1
            candidates = ((candidate, True) for candidate in found)
        elif path is not None and path.is_file():
            candidates = ((path, False),)
        else:
            print(f"Path not found: {value}", file=sys.stderr)
            errors += 1
            continue
        for candidate, from_folder in candidates:
            resolved = candidate.resolve()
            key = os.path.normcase(str(resolved))
            if key not in seen:
                seen.add(key)
                files.append((resolved, from_folder))
    return files, errors


def work_base_for_input(path, from_folder):
    default = ROOT / "work" / path.parent.name
    if not from_folder:
        return default
    game_root = ROOT.parent / "games"
    if (path.name.casefold() == "strings.json" and
            os.path.normcase(str(path.parent.parent.resolve())) ==
            os.path.normcase(str(game_root.resolve()))):
        return default
    identity = os.path.normcase(str(path.resolve())).encode("utf-8")
    suffix = hashlib.sha256(identity).hexdigest()[:12]
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", path.parent.name)
    return ROOT / "work" / f"{safe_name}-{suffix}"


def active_checkpoints(path, from_folder):
    work_base = work_base_for_input(path, from_folder)
    if not work_base.is_dir():
        return []
    return sorted((checkpoint for model_dir in work_base.iterdir() if model_dir.is_dir()
                   for name in ("stream-checkpoint.json", "translations.json")
                   if (checkpoint := model_dir / name).is_file()), key=str)


def archive_checkpoint(path):
    number = 0
    while True:
        suffix = ".cleared" if number == 0 else f".cleared.{number}"
        archive = path.with_name(path.stem + suffix + path.suffix)
        if not archive.exists():
            path.rename(archive)
            return archive
        number += 1


def replace_bytes(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
        os.chmod(temporary, path.stat().st_mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def checkpoint_snapshot(path, from_folder):
    return tuple((checkpoint, hashlib.sha256(checkpoint.read_bytes()).digest())
                 for checkpoint in active_checkpoints(path, from_folder))


def inspect_file(path, from_folder=False):
    raw = path.read_bytes()
    _, count = cleared_bytes(raw)
    return ClearPlan(path, from_folder, hashlib.sha256(raw).digest(), count,
                     checkpoint_snapshot(path, from_folder))


def clear_file(plan, confirmed=False):
    path = plan.path
    if not plan.fields and not plan.checkpoints:
        print(f"Already clear: {path}")
        return "unchanged"
    if not confirmed:
        print(f"{path}\n{plan.fields} translated en field(s) will be cleared; "
              f"{len(plan.checkpoints)} active checkpoint(s) will be archived.")
        try:
            answer = input("Type CLEAR to confirm this file (Enter skips): ")
        except EOFError:
            answer = ""
        if answer != "CLEAR":
            print(f"Skipped: {path}")
            return "skipped"
    raw = path.read_bytes()
    if hashlib.sha256(raw).digest() != plan.source_sha256:
        raise ValueError("file changed while waiting for confirmation")
    if checkpoint_snapshot(path, plan.from_folder) != plan.checkpoints:
        raise ValueError("checkpoint changed while waiting for confirmation")
    result, count = cleared_bytes(raw)
    if count != plan.fields:
        raise ValueError("English field count changed while waiting for confirmation")
    if count:
        replace_bytes(path, result)
    for checkpoint, _digest in plan.checkpoints:
        archive = archive_checkpoint(checkpoint)
        print(f"Archived checkpoint: {archive}")
    print(f"Cleared {count} field(s) and retired {len(plan.checkpoints)} checkpoint(s): {path}")
    return "cleared"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="script files or folders to scan recursively")
    parser.add_argument("--batch-from-env", action="store_true",
                        help="read dropped paths from the batch launcher")
    args = parser.parse_args()
    if args.batch_from_env and args.paths:
        parser.error("choose dropped paths or command-line paths")
    try:
        paths = dropped_paths() if args.batch_from_env else args.paths
    except ValueError as exc:
        parser.error(str(exc))
    if not paths:
        parser.error("provide a script file or folder")
    files, errors = collect_files(paths)
    print(f"Found {len(files)} script file(s).")
    counts = {"cleared": 0, "skipped": 0, "unchanged": 0}
    plans = []
    for path, from_folder in files:
        try:
            plan = inspect_file(path, from_folder)
            if plan.fields or plan.checkpoints:
                plans.append(plan)
            else:
                print(f"Already clear: {path}")
                counts["unchanged"] += 1
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            print(f"Failed: {path}: {exc}", file=sys.stderr)
            errors += 1
    if errors and len(files) > 1:
        print("Preflight failed; no files were cleared.", file=sys.stderr)
        return 1
    if len(plans) > 1:
        for plan in plans:
            print(f"{plan.path}: {plan.fields} English field(s), "
                  f"{len(plan.checkpoints)} checkpoint(s)")
        print(f"Total: {len(plans)} files, {sum(plan.fields for plan in plans)} English "
              f"field(s), {sum(len(plan.checkpoints) for plan in plans)} checkpoint(s).")
        try:
            answer = input("Type CLEAR ALL to confirm this batch (Enter skips): ")
        except EOFError:
            answer = ""
        if answer != "CLEAR ALL":
            counts["skipped"] += len(plans)
            print("Batch skipped; no files were cleared.")
            plans = []
        else:
            for plan in plans:
                try:
                    counts[clear_file(plan, confirmed=True)] += 1
                except (OSError, UnicodeError, ValueError, TypeError) as exc:
                    print(f"Failed: {plan.path}: {exc}", file=sys.stderr)
                    errors += 1
            plans = []
    for plan in plans:
        try:
            counts[clear_file(plan)] += 1
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            print(f"Failed: {plan.path}: {exc}", file=sys.stderr)
            errors += 1
    print(f"Finished: {counts['cleared']} cleared, {counts['skipped']} skipped, "
          f"{counts['unchanged']} already clear, {errors} error(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
