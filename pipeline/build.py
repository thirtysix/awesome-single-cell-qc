#!/usr/bin/env python3
"""Stage 3 - validate the hand-written records and assemble the catalog.

Reads every curation/records/*.yaml (a YAML list under the key `records:`),
validates each record against curation/schema.yaml, resolves benchmark
references against curation/benchmarks.yaml, merges in whatever the network
stages have cached (citation counts, repository activity, publication metadata,
the citation check), and writes the two artefacts everything else is generated
from:

    data/catalog.json   full records plus derived fields, and summary counts
    data/catalog.tsv    flat table, one row per record

Offline: it only reads caches, so it never needs a network or an API key.

    python pipeline/build.py [--records PATH] [--benchmarks FILE] [--strict]

`--records` takes a directory of *.yaml files or a single file, so the tests
and `make curate FIXTURES=1` can build from tests/fixtures/ instead of the real
records. The environment variable RECORDS_DIR does the same.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from config import (BENCHMARKS, CACHE, CATEGORY_KEYS, CATEGORY_LAYER, DATA,
                    FIELDS, GAIN_SOURCES, KINDS, LANGUAGES, LAYERS, RECORDS_DIR,
                    REQUIRED, REQUIRES, ROOT, SIDES, TIERS, is_preprint)

COLUMNS = [
    "id", "name", "kind", "layer", "categories", "primary_category", "side", "tier",
    "summary", "recovers", "gain", "gain_source", "requires", "caveats",
    "url", "repo", "repo_url", "language",
    "doi", "pmid", "cite_title", "year", "verified", "citation_check",
    "publication", "publication_url", "publication_is_preprint",
    "publication_title", "publication_venue",
    "citations", "citation_note", "citations_total", "citations_papers",
    "citations_recent", "citations_recent_year",
    "repo_stars", "repo_pushed", "repo_archived", "repo_language", "repo_license",
    "papers", "benchmarks", "qc_links", "track", "review", "tags", "source_file",
]

ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
PAPER_RE = re.compile(r"^(?:pmid:\d+|doi:10\.\d{4,9}/\S+)$")
REVIEW_RE = re.compile(r"^[A-Za-z0-9._-]+(?:#[A-Za-z0-9._-]+)?$")
# owner/name (GitHub), or host/owner/name, or a full URL to a code host.
REPO_RE = re.compile(r"^(?:https?://)?(?:[a-z0-9.-]+\.[a-z]{2,}/)?[\w.-]+/[\w.-]+/?$", re.I)
EM_DASH = "\u2014"

STRING_FIELDS = ("name", "summary", "recovers", "gain", "caveats", "url",
                 "cite_title", "track", "review")
LIST_OF_STR_FIELDS = ("tags",)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def rel(path: Path) -> str:
    """A path as a reader wants to see it in an error: relative to the repo."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def record_files(path: Path) -> list[Path]:
    """The YAML files a records path stands for: one file, or a directory's *.yaml."""
    path = Path(path)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(list(path.glob("*.yaml")) + list(path.glob("*.yml")))
    return []


def load_record_files(path: Path) -> tuple[list[tuple[str, list]], list[str]]:
    """[(file, records)] for every records file, plus load errors.

    An empty file is accepted as zero records, because a research track may
    create its file before it has written anything. A file with content but no
    `records:` key is an error: it is almost certainly a typo'd key, and
    silently reading it as empty would drop everything in it.
    """
    out, errors = [], []
    for f in record_files(path):
        name = rel(f)
        try:
            blob = yaml.safe_load(f.read_text())
        except yaml.YAMLError as exc:
            errors.append(f"{name}: not valid YAML ({str(exc).splitlines()[0]})")
            continue
        if blob is None:
            out.append((name, []))
            continue
        if not isinstance(blob, dict) or "records" not in blob:
            errors.append(f"{name}: expected a top-level key `records:` holding a list")
            continue
        recs = blob.get("records") or []
        if not isinstance(recs, list):
            errors.append(f"{name}: `records:` must be a list")
            continue
        out.append((name, recs))
    return out, errors


def load_benchmarks(path: Path) -> tuple[list[dict], list[str]]:
    """Benchmark studies from curation/benchmarks.yaml (key `benchmarks:`), validated."""
    path = Path(path)
    if not path.exists():
        return [], []
    try:
        blob = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        return [], [f"{rel(path)}: not valid YAML ({str(exc).splitlines()[0]})"]
    items = blob.get("benchmarks") if isinstance(blob, dict) else None
    if items is None:
        return [], []
    if not isinstance(items, list):
        return [], [f"{rel(path)}: `benchmarks:` must be a list"]
    errors, seen, out = [], {}, []
    allowed = {"id", "name", "doi", "pmid", "cite_title", "year", "scope", "verified",
               "url", "categories", "notes"}
    for i, b in enumerate(items, 1):
        where = f"{rel(path)} benchmark {i}"
        if not isinstance(b, dict):
            errors.append(f"{where}: must be a mapping")
            continue
        bid = b.get("id")
        where = f"{where} (id '{bid}')"
        if not isinstance(bid, str) or not ID_RE.match(bid):
            errors.append(f"{where}: id must be a lowercase slug of [a-z0-9-]")
        elif bid in seen:
            errors.append(f"duplicate benchmark id '{bid}': {seen[bid]} and {where}")
        else:
            seen[bid] = where
        if not isinstance(b.get("name"), str) or not b.get("name", "").strip():
            errors.append(f"{where}: missing required field 'name'")
        for key in b:
            if key not in allowed:
                errors.append(f"{where}: unknown field '{key}' (allowed: {', '.join(sorted(allowed))})")
        errors += _check_identifiers(b, where)
        if "verified" in b and not isinstance(b["verified"], bool):
            errors.append(f"{where}: verified must be true or false")
        for c in b.get("categories") or []:
            if c not in CATEGORY_KEYS:
                errors.append(f"{where}: category '{c}' not in schema categories")
        out.append(b)
    return out, errors


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _check_identifiers(rec: dict, where: str) -> list[str]:
    errors = []
    doi = rec.get("doi")
    if doi is not None and doi != "":
        if not isinstance(doi, str) or not DOI_RE.match(doi.strip()):
            hint = (" (store it bare: drop the https://doi.org/ or doi: prefix)"
                    if isinstance(doi, str) and ("doi.org" in doi or doi.lower().startswith("doi:"))
                    else "")
            errors.append(f"{where}: doi '{doi}' is not a bare DOI like 10.1234/abc{hint}")
    pmid = rec.get("pmid")
    if pmid is not None and pmid != "":
        if isinstance(pmid, bool) or not re.fullmatch(r"\d{1,9}", str(pmid).strip()):
            errors.append(f"{where}: pmid '{pmid}' must be digits only")
    year = rec.get("year")
    if year is not None and year != "":
        if isinstance(year, bool) or not re.fullmatch(r"\d{4}", str(year).strip()) \
                or not 1900 <= int(year) <= date.today().year + 1:
            errors.append(f"{where}: year '{year}' must be a four-digit year")
    return errors


def _enum(rec: dict, field: str, allowed: dict | list, label: str, where: str) -> list[str]:
    value = rec.get(field)
    if value is None or value == "":
        return []
    if value not in allowed:
        return [f"{where}: {field} '{value}' not in {label} [{', '.join(allowed)}]"]
    return []


def validate_record(rec: dict, where: str, benchmark_ids: set[str]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one record against curation/schema.yaml.

    Errors stop the build: a missing required field, a value outside the
    schema's vocabulary, a malformed id or identifier, an unknown field name
    (almost always a typo, and a typo'd optional field would otherwise vanish
    silently), or a benchmark reference that does not resolve.

    Warnings are printed and the build carries on: style rules from the schema
    and CLAUDE.md that do not make a record wrong, only untidy.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(rec, dict):
        return [f"{where}: a record must be a mapping of field: value"], []

    for field in REQUIRED:
        value = rec.get(field)
        if value is None or value == "" or value == []:
            errors.append(f"{where}: missing required field '{field}'")
    for field in rec:
        if field not in FIELDS:
            errors.append(f"{where}: unknown field '{field}' (not in curation/schema.yaml fields)")

    rid = rec.get("id")
    if rid is not None and (not isinstance(rid, str) or not ID_RE.match(rid)):
        errors.append(f"{where}: id '{rid}' must be a lowercase slug of [a-z0-9-], "
                      "not starting or ending with '-'")

    errors += _enum(rec, "kind", KINDS, "kinds", where)
    errors += _enum(rec, "layer", LAYERS, "layers", where)
    errors += _enum(rec, "side", SIDES, "sides", where)
    errors += _enum(rec, "tier", TIERS, "tiers", where)
    errors += _enum(rec, "gain_source", GAIN_SOURCES, "gain_sources", where)
    if LANGUAGES:
        errors += _enum(rec, "language", LANGUAGES, "languages", where)

    for field in STRING_FIELDS:
        if field in rec and rec[field] is not None and not isinstance(rec[field], str):
            errors.append(f"{where}: {field} must be text")

    cats = rec.get("categories")
    if cats is not None:
        if not isinstance(cats, list):
            errors.append(f"{where}: categories must be a list")
        else:
            for c in cats:
                if c not in CATEGORY_KEYS:
                    errors.append(f"{where}: category '{c}' not in schema categories")
            if len(set(map(str, cats))) != len(cats):
                errors.append(f"{where}: categories lists a key twice")
            if cats and cats[0] in CATEGORY_LAYER and rec.get("layer") in LAYERS \
                    and CATEGORY_LAYER[cats[0]] != rec["layer"]:
                warnings.append(f"{where}: primary category '{cats[0]}' is in layer "
                                f"'{CATEGORY_LAYER[cats[0]]}' but the record says "
                                f"layer '{rec['layer']}'")

    reqs = rec.get("requires")
    if reqs is not None:
        if not isinstance(reqs, list):
            errors.append(f"{where}: requires must be a list")
        else:
            for r in reqs:
                if r not in REQUIRES:
                    errors.append(f"{where}: requires '{r}' not in schema requires "
                                  f"[{', '.join(REQUIRES)}]")

    repo = rec.get("repo")
    if repo not in (None, "") and (not isinstance(repo, str) or not REPO_RE.match(repo.strip())):
        errors.append(f"{where}: repo '{repo}' should be owner/name (GitHub) or a code-host URL")
    url = rec.get("url")
    if isinstance(url, str) and url and not re.match(r"^https?://", url):
        errors.append(f"{where}: url '{url}' must start with http:// or https://")

    errors += _check_identifiers(rec, where)

    verified = rec.get("verified")
    if verified is not None and not isinstance(verified, bool):
        errors.append(f"{where}: verified must be true or false")
    if verified is True:
        if not (rec.get("doi") or rec.get("pmid")):
            errors.append(f"{where}: verified is true but there is no doi or pmid to verify")
        if not rec.get("cite_title"):
            errors.append(f"{where}: verified is true but cite_title is empty")

    papers = rec.get("papers")
    if papers is not None:
        if not isinstance(papers, list):
            errors.append(f"{where}: papers must be a list")
        else:
            for p in papers:
                if not isinstance(p, str) or not PAPER_RE.match(p.strip()):
                    errors.append(f"{where}: paper '{p}' must be 'pmid:NNN' or 'doi:10....'")

    benches = rec.get("benchmarks")
    if benches is not None:
        if not isinstance(benches, list):
            errors.append(f"{where}: benchmarks must be a list of benchmark ids")
        else:
            for b in benches:
                if b not in benchmark_ids:
                    errors.append(f"{where}: benchmark '{b}' is not an id in "
                                  "curation/benchmarks.yaml")

    links = rec.get("qc_links")
    if links is not None:
        if not isinstance(links, list):
            errors.append(f"{where}: qc_links must be a list of {{category, effect}}")
        else:
            for link in links:
                if not isinstance(link, dict) or set(link) - {"category", "effect"}:
                    errors.append(f"{where}: each qc_links entry is {{category, effect}}")
                    continue
                if link.get("category") not in CATEGORY_KEYS:
                    errors.append(f"{where}: qc_links category '{link.get('category')}' "
                                  "not in schema categories")
                if not isinstance(link.get("effect"), str) or not link.get("effect"):
                    errors.append(f"{where}: qc_links entry needs an effect")

    review = rec.get("review")
    if isinstance(review, str) and review and not REVIEW_RE.match(review):
        errors.append(f"{where}: review '{review}' should look like 01-demux-recovery#demuxmix")

    for field in LIST_OF_STR_FIELDS:
        value = rec.get(field)
        if value is not None and (not isinstance(value, list)
                                  or not all(isinstance(v, str) for v in value)):
            errors.append(f"{where}: {field} must be a list of text")

    # Style, not correctness.
    summary = rec.get("summary")
    if isinstance(summary, str) and summary.rstrip().endswith("."):
        warnings.append(f"{where}: summary ends with a full stop (schema: no trailing full stop)")
    for field, value in rec.items():
        if isinstance(value, str) and EM_DASH in value:
            warnings.append(f"{where}: {field} contains an em-dash")
    if rec.get("gain") and not rec.get("gain_source"):
        warnings.append(f"{where}: gain is given without a gain_source")
    return errors, warnings


def validate_records(files: list[tuple[str, list]], benchmark_ids: set[str]
                     ) -> tuple[list[dict], list[str], list[str]]:
    """Validate every record; ids must be unique across ALL files.

    A duplicate is reported with both locations, because the two copies are
    usually in different research tracks' files and the fix is to merge them.
    """
    records, errors, warnings = [], [], []
    seen: dict[str, str] = {}
    for fname, recs in files:
        for i, rec in enumerate(recs, 1):
            rid = rec.get("id") if isinstance(rec, dict) else None
            where = f"{fname} record {i}" + (f" (id '{rid}')" if rid else "")
            errs, warns = validate_record(rec, where, benchmark_ids)
            errors += errs
            warnings += warns
            if isinstance(rid, str) and rid:
                if rid in seen:
                    errors.append(f"duplicate id '{rid}': {seen[rid]} and {where}")
                else:
                    seen[rid] = where
            if not errs:
                records.append({**rec, "_source": fname})
    return records, errors, warnings


# ---------------------------------------------------------------------------
# Caches written by the network stages
# ---------------------------------------------------------------------------
def cache_key(ident: str) -> str:
    kind, _, value = ident.partition(":")
    return f"{kind}_{value}".replace("/", "_").replace(":", "_")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        blob = json.loads(path.read_text())
    except ValueError:
        return {}
    return blob if isinstance(blob, dict) else {}


def load_citation_counts(cache_dir: Path = CACHE) -> dict[str, int]:
    """Per-identifier citation counts from the enrichment cache."""
    counts: dict[str, int] = {}
    path = Path(cache_dir) / "citation_cache.csv"
    if path.exists():
        with path.open() as fh:
            for row in csv.reader(fh):
                if len(row) >= 2 and row[0] != "identifier":
                    try:
                        counts[row[0]] = int(row[1])
                    except ValueError:
                        continue
    return counts


def load_github_cache(cache_dir: Path = CACHE) -> dict[str, dict]:
    """Repository metadata keyed by slug, written by enrich.py."""
    return _read_json(Path(cache_dir) / "github.json")


def load_pubmeta(cache_dir: Path = CACHE) -> dict[str, dict]:
    """Identifier key -> {year, title, venue, by_year, pmid, doi}, from fill_metadata.py."""
    return _read_json(Path(cache_dir) / "pubmeta.json")


def load_verify(cache_dir: Path = CACHE) -> dict[str, dict]:
    """'record:<id>' / 'benchmark:<id>' -> citation-check entry, from verify_citations.py."""
    return _read_json(Path(cache_dir) / "verify.json").get("entries") or {}


def recent_citations(meta: dict, build_year: int) -> tuple[int | None, str]:
    """Citations received in the last COMPLETE calendar year.

    Not the current year: OpenAlex reports it partially, so using the running
    year would understate every paper by roughly half and do it unevenly, since
    indexing lag differs by venue. It reads low for a genuinely new method,
    whose first full year has not happened yet; that is a real limitation, and
    the reason the column sits beside the total rather than replacing it.
    """
    by_year = (meta or {}).get("by_year") or {}
    if not by_year:
        return None, ""
    year = str(build_year - 1)
    # OpenAlex OMITS a year with no citations rather than recording a zero, so a
    # missing year in a populated series means zero, not unknown.
    return by_year.get(year, 0), year


def publication_url(ident: str) -> str:
    """A link a reader can follow, rather than `pmid:30902100`."""
    if ident.startswith("pmid:"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{ident[5:]}/"
    if ident.startswith("doi:"):
        return f"https://doi.org/{ident[4:]}"
    return ""


def identifiers(rec: dict) -> list[str]:
    """The record's own paper as identifiers, DOI first.

    DOI first because it names one work unambiguously: OpenAlex holds duplicate
    records for some papers and a PMID can land on the lower-cited copy (the
    upstream catalog's Segway case: 290 citations by PMID, 663 by DOI).
    """
    out = []
    if rec.get("doi"):
        out.append(f"doi:{str(rec['doi']).strip()}")
    if rec.get("pmid"):
        out.append(f"pmid:{str(rec['pmid']).strip()}")
    return out


def repo_url(repo: str) -> str:
    repo = (repo or "").strip().rstrip("/")
    if not repo:
        return ""
    if re.match(r"^https?://", repo):
        return repo
    if repo.count("/") >= 2:                     # host/owner/name
        return f"https://{repo}"
    return f"https://github.com/{repo}"


def github_slug(repo: str) -> str:
    """owner/name when the repository is on GitHub, else ""."""
    repo = (repo or "").strip().rstrip("/")
    m = re.match(r"^(?:https?://)?(?:www\.)?github\.com/([\w.-]+/[\w.-]+)", repo, re.I)
    if m:
        return re.sub(r"\.git$", "", m.group(1))
    if repo.count("/") == 1 and not re.match(r"^https?://", repo):
        return repo
    return ""


def apply_verified_publications(row: dict, papers: list[str], cites: dict[str, int]) -> str:
    """Total a record's citations across its own papers.

    `papers` is the record's primary identifier plus its `papers:` list, all of
    which the curator has put there as the method's OWN work. The headline
    `citations` stays the primary paper's count, because that is the paper the
    record's doi/pmid names and the citation check verified; the sum lands in
    `citations_total` and is only ever displayed as "across N papers". Nothing
    sorts on the total, because it is not comparable with single-paper counts.

    Deduplicated: the same work listed twice must not be counted twice.
    Returns a note on what could not be counted.
    """
    counts = {}
    for ident in dict.fromkeys(papers):
        c = cites.get(cache_key(ident))
        if c is not None:
            counts[ident] = c
    if len(counts) < 2:
        return ""
    row["citations_total"] = sum(counts.values())
    row["citations_papers"] = len(counts)
    missing = len(dict.fromkeys(papers)) - len(counts)
    return f"{missing} listed paper(s) had no citation count" if missing else ""


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def verify_state(entry: dict | None, rec: dict) -> str:
    """The citation-check status, but only if it was made against these identifiers.

    A check made before the doi, pmid or title was edited says nothing about
    the record as it now stands, so a stale entry reads as unchecked.
    """
    if not entry:
        return ""
    same = (str(entry.get("doi") or "") == str(rec.get("doi") or "")
            and str(entry.get("pmid") or "") == str(rec.get("pmid") or "")
            and (entry.get("cite_title") or "") == (rec.get("cite_title") or ""))
    return entry.get("status", "") if same else "stale"


def from_record(rec: dict, cites: dict[str, int], shared: Counter,
                gh: dict[str, dict], pubmeta: dict[str, dict],
                bench_index: dict[str, dict], verify: dict[str, dict],
                build_year: int) -> dict:
    """One catalog row from one validated record.

    Every field the record states is carried through unchanged; the rest is
    derived from the caches, and a blank derived field always says why.
    """
    ids = identifiers(rec)
    primary = ids[0] if ids else ""
    n_sharing = max((shared.get(i, 0) for i in ids), default=0)
    if n_sharing >= 3:
        # A paper claimed as primary by three or more records is a suite or
        # platform paper, and crediting each member with its total is the error
        # the upstream catalog spent most of its citation work undoing.
        citations, note = None, f"primary publication shared by {n_sharing} records"
    else:
        # Unknown is not zero: enrich.py leaves an unresolved lookup absent.
        citations = next((cites[cache_key(i)] for i in ids if cache_key(i) in cites), None)
        note = ""
        if citations is None:
            note = ("no publication recorded" if not ids
                    else "no citation count yet (run make enrich; or not indexed by OpenAlex)")

    meta = {}
    for i in ids:
        meta = pubmeta.get(cache_key(i)) or {}
        if meta:
            break
    slug = github_slug(rec.get("repo") or "")
    info = (gh.get(slug) or {}) if slug else {}
    if info.get("status") != "ok":
        info = {}

    year = rec.get("year") or meta.get("year") or ""
    recent, ryear = recent_citations(meta, build_year)
    row = {
        "id": rec["id"],
        "name": rec["name"],
        "kind": rec["kind"],
        "layer": rec["layer"],
        "categories": list(rec["categories"]),
        "primary_category": rec["categories"][0],
        "side": rec["side"],
        "tier": rec["tier"],
        "summary": rec["summary"].strip(),
        "recovers": rec.get("recovers") or "",
        "gain": rec.get("gain") or "",
        "gain_source": rec.get("gain_source") or "",
        "requires": list(rec.get("requires") or []),
        "caveats": rec.get("caveats") or "",
        "url": rec.get("url") or "",
        "repo": rec.get("repo") or "",
        "repo_url": repo_url(rec.get("repo") or ""),
        "language": rec.get("language") or "",
        "doi": str(rec.get("doi") or "") or meta.get("doi", ""),
        "pmid": str(rec.get("pmid") or "") or meta.get("pmid", ""),
        "cite_title": rec.get("cite_title") or "",
        "year": str(year),
        "verified": rec.get("verified") is True,
        "citation_check": verify_state(verify.get(f"record:{rec['id']}"), rec),
        "publication": primary,
        "publication_url": publication_url(primary),
        "publication_is_preprint": is_preprint(primary),
        "publication_title": rec.get("cite_title") or meta.get("title", ""),
        "publication_venue": meta.get("venue", ""),
        "citations": citations,
        "citation_note": note,
        "citations_total": None,
        "citations_papers": None,
        "citations_recent": recent,
        "citations_recent_year": ryear,
        "repo_stars": info.get("stars"),
        "repo_pushed": info.get("pushed_at") or "",
        "repo_archived": info.get("archived"),
        "repo_language": info.get("language") or "",
        "repo_license": info.get("license") or "",
        "papers": list(rec.get("papers") or []),
        "benchmarks": list(rec.get("benchmarks") or []),
        "benchmark_refs": [{"id": b, "name": bench_index[b].get("name", b),
                            "url": benchmark_url(bench_index[b])}
                           for b in rec.get("benchmarks") or [] if b in bench_index],
        "qc_links": list(rec.get("qc_links") or []),
        "track": rec.get("track") or "",
        "review": rec.get("review") or "",
        "tags": list(rec.get("tags") or []),
        "source_file": rec.get("_source", ""),
    }
    if citations is not None and row["papers"]:
        extra = apply_verified_publications(row, [primary] + row["papers"], cites)
        if extra:
            row["citation_note"] = extra
    return row


def benchmark_url(b: dict) -> str:
    if b.get("doi"):
        return f"https://doi.org/{b['doi']}"
    if b.get("pmid"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{b['pmid']}/"
    return b.get("url") or ""


def build_catalog(records_path: Path = RECORDS_DIR, benchmarks_path: Path = BENCHMARKS,
                  cache_dir: Path = CACHE) -> tuple[dict, list[str], list[str]]:
    """(catalog, errors, warnings). The catalog is None-free only when errors is empty."""
    benchmarks, errors = load_benchmarks(benchmarks_path)
    bench_index = {b["id"]: b for b in benchmarks if isinstance(b.get("id"), str)}
    files, load_errors = load_record_files(records_path)
    errors += load_errors
    records, rec_errors, warnings = validate_records(files, set(bench_index))
    errors += rec_errors
    if errors:
        return {}, errors, warnings

    cites = load_citation_counts(cache_dir)
    gh = load_github_cache(cache_dir)
    pubmeta = load_pubmeta(cache_dir)
    verify = load_verify(cache_dir)
    build_year = date.today().year
    shared = Counter(i for r in records for i in identifiers(r))

    rows = [from_record(r, cites, shared, gh, pubmeta, bench_index, verify, build_year)
            for r in records]
    rows.sort(key=lambda r: (-int(r["citations"] or 0), r["name"].lower()))

    evaluates: dict[str, list[str]] = {}
    for r in rows:
        for b in r["benchmarks"]:
            evaluates.setdefault(b, []).append(r["id"])
    bench_rows = [{
        "id": b["id"], "name": b.get("name", ""), "doi": str(b.get("doi") or ""),
        "pmid": str(b.get("pmid") or ""), "cite_title": b.get("cite_title") or "",
        "year": str(b.get("year") or ""), "scope": b.get("scope") or "",
        "verified": b.get("verified") is True, "url": benchmark_url(b),
        "citation_check": verify_state(verify.get(f"benchmark:{b['id']}"), b),
        "evaluates": sorted(evaluates.get(b["id"], [])),
    } for b in benchmarks]

    def counts(key: str, vocab) -> dict[str, int]:
        c = Counter(v for r in rows for v in (r[key] if isinstance(r[key], list) else [r[key]]))
        return {k: c.get(k, 0) for k in vocab}

    meta = {
        "generated": date.today().isoformat(),
        "count": len(rows),
        "records_source": rel(Path(records_path)),
        "record_files": len(files),
        "by_category": counts("categories", CATEGORY_KEYS),
        "by_primary_category": counts("primary_category", CATEGORY_KEYS),
        "by_layer": counts("layer", LAYERS),
        "by_tier": counts("tier", TIERS),
        "by_kind": counts("kind", KINDS),
        "by_side": counts("side", SIDES),
        "benchmarks": len(bench_rows),
        "verified": sum(1 for r in rows if r["verified"]),
        "with_repo": sum(1 for r in rows if r["repo_url"]),
        "with_citations": sum(1 for r in rows if r["citations"] is not None),
    }
    return {"meta": meta, "records": rows, "benchmarks": bench_rows}, [], warnings


# Kinds that may exist without a primary paper (see strict_failures).
PAPERLESS_KINDS = ("tool", "method", "design")


def strict_failures(catalog: dict, verify: dict[str, dict]) -> list[str]:
    """What `make build-strict` refuses to ship.

    Every record must be verified (doi/pmid fetched and cite_title matched),
    except a `hypothesis`, which may have no paper at all, and a tool, method
    or design that names no doi or pmid but points somewhere checkable (url,
    repo or `papers:`): it claims no primary paper, so there is nothing to
    verify. And no current entry in data/cache/verify.json may be a mismatch:
    a record can say `verified: true` and still have been contradicted by the
    last check.
    """
    out = []
    for r in catalog.get("records", []):
        paperless = (r["kind"] in PAPERLESS_KINDS and not r.get("doi") and not r.get("pmid")
                     and (r.get("url") or r.get("repo") or r.get("papers")))
        if r["tier"] != "hypothesis" and not r["verified"] and not paperless:
            out.append(f"{r['id']} ({r['source_file']}): verified is not true "
                       f"and tier is '{r['tier']}'")
        if r.get("citation_check") == "mismatch":
            reasons = "; ".join((verify.get(f"record:{r['id']}") or {}).get("reasons") or [])
            out.append(f"{r['id']} ({r['source_file']}): citation check mismatch: {reasons}")
    for b in catalog.get("benchmarks", []):
        if b.get("citation_check") == "mismatch":
            reasons = "; ".join((verify.get(f"benchmark:{b['id']}") or {}).get("reasons") or [])
            out.append(f"benchmark {b['id']}: citation check mismatch: {reasons}")
    return out


def tsv_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "|".join(f"{v.get('category')}:{v.get('effect')}" if isinstance(v, dict)
                        else str(v) for v in value)
    return re.sub(r"[\t\r\n]+", " ", str(value))


def write_catalog(catalog: dict, out_dir: Path = DATA) -> tuple[Path, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cj, ct = out_dir / "catalog.json", out_dir / "catalog.tsv"
    cj.write_text(json.dumps(catalog, indent=1, ensure_ascii=False) + "\n")
    with ct.open("w", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        w.writerow(COLUMNS)
        for r in catalog["records"]:
            w.writerow([tsv_value(r.get(c)) for c in COLUMNS])
    return cj, ct


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", type=Path,
                    default=Path(os.environ.get("RECORDS_DIR") or RECORDS_DIR),
                    help="directory of *.yaml record files, or one file "
                         "(default: $RECORDS_DIR or curation/records)")
    ap.add_argument("--benchmarks", type=Path,
                    default=Path(os.environ.get("BENCHMARKS_FILE") or BENCHMARKS),
                    help="benchmark studies file (default: curation/benchmarks.yaml)")
    ap.add_argument("--out-dir", type=Path, default=DATA,
                    help="where catalog.json and catalog.tsv go (default: data/)")
    ap.add_argument("--cache-dir", type=Path, default=CACHE)
    ap.add_argument("--strict", action="store_true",
                    help="fail on any record that is not verified (unless tier is "
                         "hypothesis) and on any mismatch in data/cache/verify.json")
    args = ap.parse_args(argv)

    if not args.records.exists():
        print(f"error: records path {args.records} does not exist", file=sys.stderr)
        return 2
    catalog, errors, warnings = build_catalog(args.records, args.benchmarks, args.cache_dir)
    for w in warnings:
        print(f"  warning: {w}")
    if errors:
        print(f"\n{len(errors)} validation error(s); nothing was written:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    if args.strict:
        failures = strict_failures(catalog, load_verify(args.cache_dir))
        if failures:
            print(f"\nbuild-strict: {len(failures)} problem(s); nothing was written:",
                  file=sys.stderr)
            for f in failures:
                print(f"  {f}", file=sys.stderr)
            return 1

    cj, ct = write_catalog(catalog, args.out_dir)
    meta = catalog["meta"]
    if meta["count"] == 0:
        print(f"catalog: 0 records ({meta['records_source']} has "
              f"{meta['record_files']} record file(s) and no records yet)")
    else:
        print(f"catalog: {meta['count']} records from {meta['record_files']} file(s) "
              f"in {meta['records_source']}; {meta['benchmarks']} benchmark(s)")
        print(f"  verified: {meta['verified']}   with repository: {meta['with_repo']}   "
              f"with citation count: {meta['with_citations']}")
        for layer in LAYERS:
            print(f"  [{layer}]")
            for k in CATEGORY_KEYS:
                if CATEGORY_LAYER[k] == layer:
                    print(f"    {k:26s} {meta['by_category'][k]:4d}")
        print("  tiers: " + ", ".join(f"{k} {v}" for k, v in meta["by_tier"].items()))
    print(f"-> {rel(cj)}, {rel(ct)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
