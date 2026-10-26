#!/usr/bin/env python3
"""Stage 2 - citation counts and repository activity for every record.

For each record (and each benchmark study):

    doi / pmid / papers  ->  OpenAlex cited_by_count   data/cache/citation_cache.csv
                                                       data/cache/openalex/*.json.gz
    repo (GitHub)        ->  stars, last push, archived, licence, language
                                                       data/cache/github.json

Everything is cached: a re-run only asks about identifiers and repositories it
has not seen, unless told to refresh. Reads OPENALEX_API_KEY and GITHUB_TOKEN
from the environment or .env.

    python pipeline/enrich.py [--records PATH] [--no-github] [--no-citations]
                              [--refresh-github] [--refresh-citations] [--backfill-works]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import requests

from build import github_slug, identifiers, load_benchmarks, load_record_files
from config import (BENCHMARKS, CACHE, GITHUB_API, OPENALEX_API, RECORDS_DIR,
                    openalex_params, openalex_tier, user_agent)

GH_CACHE = CACHE / "github.json"
CITE_CACHE = CACHE / "citation_cache.csv"
OA_DIR = CACHE / "openalex"


# ---------------------------------------------------------------------------
# GitHub
# ---------------------------------------------------------------------------
def github_token() -> str | None:
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def fetch_github(session: requests.Session, slug: str) -> dict | None:
    try:
        r = session.get(f"{GITHUB_API}/repos/{slug}", timeout=30)
    except requests.RequestException:
        return None
    if r.status_code == 404:
        return {"status": "not_found"}
    if r.status_code == 403 and "rate limit" in r.text.lower():
        reset = int(r.headers.get("X-RateLimit-Reset", 0))
        wait = max(0, reset - int(time.time())) + 5
        print(f"    rate limited; sleeping {wait}s", file=sys.stderr)
        time.sleep(min(wait, 900))
        return fetch_github(session, slug)
    if r.status_code != 200:
        return {"status": f"http_{r.status_code}"}
    d = r.json()
    return {
        "status": "ok",
        "slug": d.get("full_name"),
        "stars": d.get("stargazers_count"),
        "forks": d.get("forks_count"),
        "open_issues": d.get("open_issues_count"),
        "archived": d.get("archived"),
        "language": d.get("language"),
        "license": ((d.get("license") or {}) or {}).get("spdx_id"),
        "created_at": (d.get("created_at") or "")[:10],
        # The last push to any branch: the closest cheap proxy for "last commit".
        "pushed_at": (d.get("pushed_at") or "")[:10],
        "topics": d.get("topics") or [],
        "description": d.get("description"),
        "fetched": date.today().isoformat(),
    }


# ---------------------------------------------------------------------------
# Citations (OpenAlex)
# ---------------------------------------------------------------------------
def ident_key(ident: str) -> str:
    kind, _, value = ident.partition(":")
    return f"{kind}_{value}".replace("/", "_").replace(":", "_")


def oa_paths(key: str, oa_dir: Path | None = None) -> tuple:
    """Both spellings of a stored work: legacy plain .json and current .json.gz."""
    oa_dir = oa_dir or OA_DIR
    return oa_dir / f"{key}.json.gz", oa_dir / f"{key}.json"


def read_openalex_work(key: str, oa_dir: Path | None = None) -> dict:
    """The stored OpenAlex work for one identifier key, or {} if absent."""
    gz, plain = oa_paths(key, oa_dir)
    for path, opener in ((gz, gzip.open), (plain, open)):
        if not path.exists():
            continue
        try:
            with opener(path, "rt", encoding="utf-8") as fh:
                results = json.load(fh).get("results") or []
        except (ValueError, OSError):
            return {}
        return results[0] if results else {}
    return {}


def save_openalex_work(key: str, payload: dict, oa_dir: Path | None = None) -> None:
    """Persist the FULL response for one identifier, gzipped.

    The whole object is kept rather than the one field the citation column
    needs: re-deriving year, venue, per-year counts or the other identifier
    later would otherwise be a second pass against a metered daily budget, for
    data already in the response. fill_metadata.py reads these offline.
    """
    oa_dir = oa_dir or OA_DIR
    oa_dir.mkdir(parents=True, exist_ok=True)
    gz, plain = oa_paths(key, oa_dir)
    tmp = gz.with_suffix(".gz.tmp")
    try:
        with gzip.open(tmp, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh)
        tmp.replace(gz)
        if plain.exists():
            plain.unlink()
    except OSError:
        tmp.unlink(missing_ok=True)


def load_citation_cache() -> dict[str, int]:
    cache: dict[str, int] = {}
    if CITE_CACHE.exists():
        with CITE_CACHE.open() as fh:
            for row in csv.reader(fh):
                if len(row) >= 2 and row[0] not in ("identifier", "pmid"):
                    try:
                        cache[row[0]] = int(row[1])
                    except ValueError:
                        continue
    # Seed from any per-work OpenAlex response already on disk.
    if OA_DIR.exists():
        for path in list(OA_DIR.glob("*.json")) + list(OA_DIR.glob("*.json.gz")):
            key = path.name.removesuffix(".gz").removesuffix(".json").rstrip(".")
            if key in cache:
                continue
            work = read_openalex_work(key)
            if work:
                cache[key] = work.get("cited_by_count", 0)
    return cache


def save_citation_cache(cache: dict[str, int]) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    with CITE_CACHE.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["identifier", "citations"])
        for k, v in sorted(cache.items()):
            w.writerow([k, v])


def openalex_lookup(session: requests.Session, ident: str,
                    cache: dict[str, int]) -> tuple[int | None, dict]:
    """Citation count for one identifier, or None if it could not be resolved.

    A failed lookup must NOT be cached as 0. That makes a network error or an
    unindexed DOI indistinguishable from a genuinely uncited paper; in the
    upstream catalog 410 such zeros were hiding real counts. Leaving the key
    absent costs one retry next run and keeps "unknown" distinct from "uncited".
    """
    key = ident_key(ident)
    if key in cache:
        return cache[key], {}
    kind, _, value = ident.partition(":")
    filt = f"ids.pmid:{value}" if kind == "pmid" else f"doi:{value}"
    try:
        r = session.get(OPENALEX_API, params=openalex_params({"filter": filt}), timeout=30)
        # A 429 here is a spent daily budget, not a slow moment: OpenAlex meters
        # credits and resets at midnight UTC, so Retry-After is measured in
        # hours. Continuing would make every remaining identifier look uncited.
        if r.status_code == 429:
            wait = r.headers.get("Retry-After", "?")
            hrs = f"{int(wait)/3600:.1f}h" if str(wait).isdigit() else wait
            raise SystemExit(
                f"\nOpenAlex returned 429: the daily budget is spent.\n"
                f"  retry after {wait}s ({hrs}); the allowance resets at midnight UTC\n"
                f"  this run was {openalex_tier()}\n"
                f"  nothing already cached is lost; rerun after the reset to continue.")
        results = r.json().get("results") or [] if r.status_code == 200 else []
    except (requests.RequestException, ValueError):
        results = []
    if not results:
        return None, {}
    w = results[0]
    save_openalex_work(key, r.json())
    cache[key] = w.get("cited_by_count") or 0
    return cache[key], {"title": w.get("title"), "year": w.get("publication_year"),
                        "venue": ((w.get("primary_location") or {}).get("source") or {}).get("display_name")}


def backfill_works(session: requests.Session, idents: list[str]) -> None:
    """Fetch the full OpenAlex response for identifiers that have none stored.

    A count already in citation_cache.csv makes openalex_lookup() return without
    touching the network, so the full response is never seen again. This is the
    explicit pass for that, rather than a silent re-fetch inside a normal run.
    """
    todo = [i for i in dict.fromkeys(idents) if not read_openalex_work(ident_key(i))]
    if not todo:
        print("  every identifier already has its full OpenAlex response stored")
        return
    print(f"  {len(todo)} identifiers have no stored response ({openalex_tier()})")
    got = 0
    for n, ident in enumerate(todo, 1):
        kind, _, value = ident.partition(":")
        filt = f"ids.pmid:{value}" if kind == "pmid" else f"doi:{value}"
        try:
            r = session.get(OPENALEX_API, params=openalex_params({"filter": filt}), timeout=30)
            if r.status_code == 429:
                wait = r.headers.get("Retry-After", "?")
                print(f"    stopped at {n}/{len(todo)}: daily budget spent, "
                      f"retry after {wait}s; {got} stored so far", file=sys.stderr)
                return
            if r.status_code != 200 or not (r.json().get("results") or []):
                continue
            save_openalex_work(ident_key(ident), r.json())
            got += 1
        except (requests.RequestException, ValueError):
            continue
        time.sleep(0.11)
    print(f"  stored {got} full responses")


# ---------------------------------------------------------------------------
def collect(records_path: Path, benchmarks_path: Path) -> tuple[list[str], list[str]]:
    """(identifiers, GitHub slugs) the catalog will display, deduplicated.

    Records are read without validation: enrichment is useful even while a
    research track's file still has a schema error, and build.py reports those.
    """
    files, _ = load_record_files(records_path)
    recs = [r for _, rs in files for r in rs if isinstance(r, dict)]
    benches, _ = load_benchmarks(benchmarks_path)
    idents, slugs = [], []
    for r in recs:
        idents += identifiers(r)
        idents += [str(p).strip() for p in r.get("papers") or [] if isinstance(p, str)]
        slug = github_slug(str(r.get("repo") or ""))
        if slug:
            slugs.append(slug)
    for b in benches:
        idents += identifiers(b)
    return list(dict.fromkeys(idents)), list(dict.fromkeys(slugs))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", type=Path,
                    default=Path(os.environ.get("RECORDS_DIR") or RECORDS_DIR))
    ap.add_argument("--benchmarks", type=Path,
                    default=Path(os.environ.get("BENCHMARKS_FILE") or BENCHMARKS))
    ap.add_argument("--no-github", action="store_true")
    ap.add_argument("--no-citations", action="store_true")
    ap.add_argument("--refresh-github", action="store_true",
                    help="re-fetch every repository, not just new ones")
    ap.add_argument("--refresh-citations", action="store_true",
                    help="re-fetch citation counts for every identifier")
    ap.add_argument("--backfill-works", action="store_true",
                    help="store the full OpenAlex response for identifiers that have none, then exit")
    args = ap.parse_args(argv)

    idents, slugs = collect(args.records, args.benchmarks)
    print(f"Enriching: {len(idents)} publication identifiers, {len(slugs)} GitHub repositories")

    http = requests.Session()
    http.headers.update({"User-Agent": user_agent(), "Accept": "application/json"})

    if args.backfill_works:
        backfill_works(http, idents)
        return 0

    if not args.no_citations and idents:
        cache = load_citation_cache()
        if args.refresh_citations:
            for i in idents:
                cache.pop(ident_key(i), None)
        todo = [i for i in idents if ident_key(i) not in cache]
        print(f"  OpenAlex: {openalex_tier()}; {len(todo)} to look up, "
              f"{len(idents) - len(todo)} cached")
        found = 0
        for n, ident in enumerate(todo, 1):
            count, _ = openalex_lookup(http, ident, cache)
            found += count is not None
            if n % 50 == 0:
                print(f"    {n}/{len(todo)}", flush=True)
                save_citation_cache(cache)
            time.sleep(0.11)           # OpenAlex asks for ~10/s at most
        save_citation_cache(cache)
        if todo:
            print(f"  citations: resolved {found}/{len(todo)} "
                  "(unresolved ones are left absent, never cached as 0)")

    if not args.no_github and slugs:
        gh = requests.Session()
        gh.headers.update({"Accept": "application/vnd.github+json", "User-Agent": user_agent()})
        token = github_token()
        if token:
            gh.headers["Authorization"] = f"Bearer {token}"
            print("  GitHub: authenticated (5000 req/h)")
        else:
            print("  GitHub: unauthenticated (60 req/h); set GITHUB_TOKEN or run `gh auth login`")
        gh_cache: dict[str, dict] = json.loads(GH_CACHE.read_text()) if GH_CACHE.exists() else {}
        todo = [s for s in slugs if args.refresh_github or s not in gh_cache
                or gh_cache[s].get("status") not in ("ok", "not_found")]
        print(f"  GitHub: {len(todo)} to fetch, {len(slugs) - len(todo)} cached")
        for n, slug in enumerate(todo, 1):
            info = fetch_github(gh, slug)
            if info is not None:            # a network error is not cached
                gh_cache[slug] = info
            if n % 20 == 0:
                GH_CACHE.parent.mkdir(parents=True, exist_ok=True)
                GH_CACHE.write_text(json.dumps(gh_cache, indent=1, sort_keys=True))
        GH_CACHE.parent.mkdir(parents=True, exist_ok=True)
        GH_CACHE.write_text(json.dumps(gh_cache, indent=1, sort_keys=True))
        missing = [s for s in slugs if (gh_cache.get(s) or {}).get("status") == "not_found"]
        if missing:
            print(f"  {len(missing)} repositories not found on GitHub: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
