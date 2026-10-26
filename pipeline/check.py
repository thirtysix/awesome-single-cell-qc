#!/usr/bin/env python3
"""Sanity checks on the built catalog and the files around it. Offline.

1. data/catalog.json exists, ids are unique; counts per layer, category and tier
   are printed.
2. Every record link in docs/review/*.md, [label](../records.md#id) or [[id]],
   names a record in the catalog; so does every [[id]] in the files
   .publish-gate-allow exempts from the publish gate's house-memory-link rule
   (tests/ aside, which carry bad ids on purpose). That rule exists to catch
   private memory links, and here only record ids may wear its syntax.
3. Denylist: if .denylist.local exists, no file that is (or would be) tracked
   by git contains any of its lines. Matching is a case-insensitive substring;
   blank lines and lines starting with # are ignored. A hit is reported by
   file, line and denylist entry NUMBER, never by the term itself, so the
   output is safe to paste anywhere.
4. Recall: how many of curation/expected.yaml's entries the catalog has
   (informational; it does not fail the check).

    python pipeline/check.py [--catalog FILE] [--review-dir DIR]

Exits 1 on any failure in 1-3.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from config import (CATEGORY_KEYS, CATEGORY_LAYER, DATA, EXPECTED, LAYERS, RECORDS_DIR,
                    REVIEW_DIR, ROOT, TIERS)

LINK_RE = re.compile(r"\[\[([^\[\]|#]+?)(?:[|#][^\[\]]*)?\]\]"
                     r"|\[[^\[\]]+\]\(\s*(?:\.\./)?records\.md#([^)\s]+)\s*\)")
# The publish gate's house-memory-link pattern, and the file that scopes its opt-out.
WIKI_LINK = re.compile(r"\[\[([a-z0-9][a-z0-9-]{3,})\]\]")
GATE_ALLOW = ROOT / ".publish-gate-allow"
GATE_RULE = "house-memory-link"
FENCE_RE = re.compile(r"^(```|~~~).*?^\1", re.S | re.M)
DENYLIST = ROOT / ".denylist.local"
# Never scanned: the denylist itself, and directories that are not content.
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".venv", "node_modules"}


def review_links(text: str) -> list[tuple[int, str]]:
    """(line number, id) for every record link, ignoring fenced code blocks.

    `[label](../records.md#id)`, `[[id]]`, `[[id|label]]` and `[[id#anchor]]`
    are accepted and resolve on the id.
    """
    blanked = FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    out = []
    for n, line in enumerate(blanked.splitlines(), 1):
        for m in LINK_RE.finditer(line):
            out.append((n, (m.group(1) or m.group(2)).strip()))
    return out


def check_review_links(review_dir: Path, record_ids: set[str],
                       benchmark_ids: set[str] = frozenset()) -> list[str]:
    problems = []
    review_dir = Path(review_dir)
    if not review_dir.is_dir():
        return problems
    for path in sorted(review_dir.glob("*.md")):
        for n, rid in review_links(path.read_text()):
            if rid not in record_ids:
                hint = (" (that is a benchmark id; record links must name a record)"
                        if rid in benchmark_ids else "")
                problems.append(f"{path.name}:{n}: link to {rid} is not a record id{hint}")
    return problems


def gate_allow_globs(path: Path = GATE_ALLOW) -> list[str]:
    """Path globs .publish-gate-allow exempts from house-memory-link."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        parts = line.split("#", 1)[0].split()
        if len(parts) == 2 and parts[0] == GATE_RULE:
            out.append(parts[1])
    return out


def source_record_ids(records_dir: Path = RECORDS_DIR) -> set[str]:
    """Record ids straight from curation/records/*.yaml. The exempted files are
    the repository's own, so they resolve against its records, not against
    whichever catalog (a fixture one, say) is being checked."""
    ids = set()
    for path in sorted(Path(records_dir).glob("*.yaml")):
        blob = yaml.safe_load(path.read_text()) or {}
        for r in (blob.get("records") or []) if isinstance(blob, dict) else []:
            if isinstance(r, dict) and r.get("id"):
                ids.add(str(r["id"]))
    return ids


def check_wiki_links(files: list[Path], globs: list[str], record_ids: set[str],
                     root: Path = ROOT) -> list[str]:
    """file:line for each [[x]] in an exempted file where x is not a record id."""
    problems = []
    for path in files:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel.startswith("tests/") or not any(fnmatch.fnmatch(rel, g) for g in globs):
            continue
        try:
            text = path.read_text()
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in WIKI_LINK.finditer(line):
                if m.group(1) not in record_ids:
                    problems.append(f"{rel}:{n}: [[{m.group(1)}]] is not a record id, "
                                    "and the publish gate is told to let it through")
    return problems


def candidate_files(root: Path = ROOT) -> list[Path]:
    """Files git tracks or would track: `git ls-files --cached --others --exclude-standard`.

    Untracked-but-not-ignored files are included on purpose: the check is
    meant to run BEFORE a commit, when the leak is still avoidable. Without git
    it falls back to a walk that honours the simple patterns in .gitignore.
    """
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached",
                              "--others", "--exclude-standard"],
                             capture_output=True, text=True, timeout=30)
        if out.returncode == 0:
            return [root / p for p in out.stdout.split("\0") if p]
    except (OSError, subprocess.SubprocessError):
        pass
    patterns = []
    gi = root / ".gitignore"
    if gi.exists():
        patterns = [p.strip() for p in gi.read_text().splitlines()
                    if p.strip() and not p.startswith("#")]
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS
                       and not _ignored(str(rel_dir / d) + "/", d + "/", patterns)]
        for f in filenames:
            if not _ignored(str(rel_dir / f), f, patterns):
                files.append(Path(dirpath) / f)
    return files


def _ignored(relpath: str, name: str, patterns: list[str]) -> bool:
    relpath = relpath.removeprefix("./")
    for p in patterns:
        p = p.lstrip("/")
        if fnmatch.fnmatch(name, p) or fnmatch.fnmatch(relpath, p):
            return True
    return False


def load_denylist(path: Path = DENYLIST) -> list[tuple[int, str]]:
    if not path.exists():
        return []
    out = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        term = line.strip()
        if term and not term.startswith("#"):
            out.append((n, term.lower()))
    return out


def check_denylist(files: list[Path], terms: list[tuple[int, str]],
                   root: Path = ROOT) -> list[str]:
    """file:line hits, naming the denylist entry by number only."""
    hits = []
    if not terms:
        return hits
    for path in files:
        if path.name == DENYLIST.name or not path.is_file():
            continue
        try:
            text = path.read_bytes()
        except OSError:
            continue
        if b"\0" in text[:8192]:
            continue                       # binary
        lines = text.decode("utf-8", errors="replace").lower().splitlines()
        for ln, line in enumerate(lines, 1):
            for n, term in terms:
                if term in line:
                    try:
                        shown = path.relative_to(root)
                    except ValueError:
                        shown = path
                    hits.append(f"{shown}:{ln}: matches denylist entry #{n}")
    return hits


def expected_recall(catalog: dict, path: Path = EXPECTED) -> tuple[int, list[str]]:
    """(entries expected, ids missing). Entries are ids, or {id: ..., ...} mappings."""
    if not path.exists():
        return 0, []
    blob = yaml.safe_load(path.read_text()) or {}
    items = blob.get("expected") or [] if isinstance(blob, dict) else []
    want = [i.get("id") if isinstance(i, dict) else str(i) for i in items]
    want = [w for w in want if w]
    have = {r["id"] for r in catalog.get("records") or []}
    return len(want), [w for w in want if w not in have]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", type=Path, default=DATA / "catalog.json")
    ap.add_argument("--review-dir", type=Path,
                    default=Path(os.environ.get("REVIEW_DIR") or REVIEW_DIR))
    ap.add_argument("--expected", type=Path, default=EXPECTED)
    args = ap.parse_args(argv)

    failures: list[str] = []
    if not args.catalog.exists():
        print(f"FAIL: {args.catalog} not found; run `make build` first", file=sys.stderr)
        return 1
    catalog = json.loads(args.catalog.read_text())
    records = catalog.get("records") or []
    ids = [r["id"] for r in records]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        failures.append(f"duplicate ids in the catalog: {', '.join(dupes)}")
    if catalog.get("meta", {}).get("count") != len(records):
        failures.append("meta.count disagrees with the number of records")

    meta = catalog.get("meta", {})
    print(f"catalog: {len(records)} records from {meta.get('records_source', '?')}, "
          f"built {meta.get('generated', '?')}")
    if not records:
        print("  (no records yet)")
    by_cat = meta.get("by_category") or {}
    for layer in LAYERS:
        n_layer = (meta.get("by_layer") or {}).get(layer, 0)
        print(f"  [{layer}] {n_layer}")
        for k in CATEGORY_KEYS:
            if CATEGORY_LAYER[k] == layer:
                print(f"    {k:26s} {by_cat.get(k, 0):4d}")
    print("  tiers: " + ", ".join(f"{k} {(meta.get('by_tier') or {}).get(k, 0)}" for k in TIERS))

    bench_ids = {b["id"] for b in catalog.get("benchmarks") or []}
    link_problems = check_review_links(args.review_dir, set(ids), bench_ids)
    n_chapters = len(list(Path(args.review_dir).glob("*.md"))) if Path(args.review_dir).is_dir() else 0
    print(f"review links: {n_chapters} chapter(s) in {args.review_dir}, "
          f"{len(link_problems)} unresolved")
    failures += link_problems

    files = candidate_files()
    globs = gate_allow_globs()
    wiki_problems = check_wiki_links(files, globs, source_record_ids()) if globs else []
    print(f"gate opt-out: {len(globs)} glob(s) in {GATE_ALLOW.name}, "
          f"{len(wiki_problems)} [[x]] naming no record")
    failures += wiki_problems

    terms = load_denylist()
    if terms:
        hits = check_denylist(files, terms)
        print(f"denylist: {len(terms)} entries, {len(files)} files scanned, {len(hits)} hit(s)")
        failures += hits
    else:
        print("denylist: no .denylist.local, skipped")

    n_expected, missing = expected_recall(catalog, args.expected)
    if n_expected:
        print(f"recall: {n_expected - len(missing)}/{n_expected} expected entries present"
              + (f"; missing: {', '.join(missing)}" if missing else ""))

    if failures:
        print(f"\nFAIL: {len(failures)} problem(s)", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("check ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
