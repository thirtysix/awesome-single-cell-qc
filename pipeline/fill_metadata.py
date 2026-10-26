#!/usr/bin/env python3
"""Stage 2b - publication metadata the records do not state.

For every record and benchmark paper: year, title, venue, per-year citation
counts, and the identifier the record did not give (a DOI for a PMID-only
record and vice versa). build.py uses it to backfill `year` where a record
leaves it out, to show the venue, and for "citations last full year".

Mostly offline: enrich.py stores the full OpenAlex response for every
identifier it looks up, and this reads those. Only an identifier with no stored
response is fetched, one request each.

    python pipeline/fill_metadata.py [--records PATH] [--refresh]

Writes data/cache/pubmeta.json.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

from build import cache_key
from config import BENCHMARKS, CACHE, OPENALEX_API, RECORDS_DIR, openalex_params, user_agent
from enrich import collect, read_openalex_work

PUBMETA = CACHE / "pubmeta.json"


def clean_title(text: str) -> str:
    """Strip the markup OpenAlex leaves in titles ("<i>de novo</i>")."""
    text = re.sub(r"<[^>]+>", "", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def work_meta(w: dict) -> dict:
    """The fields the catalog shows, from one OpenAlex work object."""
    if not w:
        return {}
    venue = ((w.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
    by_year = {str(c["year"]): c.get("cited_by_count") or 0
               for c in (w.get("counts_by_year") or []) if c.get("year")}
    # Both identifiers for one work, from OpenAlex's own ID mapping rather than
    # a title match, so it carries no matching risk.
    ids = w.get("ids") or {}
    return {"year": str(w.get("publication_year") or ""),
            "title": clean_title(w.get("title") or ""),
            "venue": clean_title(venue),
            "by_year": by_year,
            "pmid": (ids.get("pmid") or "").rstrip("/").split("/")[-1],
            "doi": (ids.get("doi") or "").removeprefix("https://doi.org/")}


def openalex_work(session: requests.Session, ident: str) -> dict:
    """Year, title, venue, per-year counts and both ids, in a single request."""
    kind, _, value = ident.partition(":")
    filt = f"ids.pmid:{value}" if kind == "pmid" else f"doi:{value}"
    try:
        r = session.get(OPENALEX_API, params=openalex_params(
            {"filter": filt,
             "select": "publication_year,title,primary_location,counts_by_year,ids"}),
            timeout=30)
        if r.status_code == 429:
            raise SystemExit("OpenAlex daily budget spent; rerun after midnight UTC")
        results = r.json().get("results") or [] if r.status_code == 200 else []
    except (requests.RequestException, ValueError):
        return {}
    return work_meta(results[0]) if results else {}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", type=Path,
                    default=Path(os.environ.get("RECORDS_DIR") or RECORDS_DIR))
    ap.add_argument("--benchmarks", type=Path,
                    default=Path(os.environ.get("BENCHMARKS_FILE") or BENCHMARKS))
    ap.add_argument("--refresh", action="store_true",
                    help="re-ask OpenAlex for identifiers already in pubmeta.json")
    args = ap.parse_args(argv)

    idents, _ = collect(args.records, args.benchmarks)
    meta = json.loads(PUBMETA.read_text()) if PUBMETA.exists() else {}
    stored = fetched = 0
    session = None
    for ident in idents:
        key = cache_key(ident)
        work = read_openalex_work(key)
        if work:
            meta[key] = work_meta(work)
            stored += 1
            continue
        if key in meta and not args.refresh:
            continue
        if session is None:
            session = requests.Session()
            session.headers.update({"User-Agent": user_agent()})
        # An empty answer is cached too, so an unindexed paper is not re-asked
        # on every run; --refresh asks again.
        meta[key] = openalex_work(session, ident)
        fetched += 1
        time.sleep(0.11)
    PUBMETA.parent.mkdir(parents=True, exist_ok=True)
    PUBMETA.write_text(json.dumps(meta, indent=1, sort_keys=True))
    with_year = sum(1 for i in idents if (meta.get(cache_key(i)) or {}).get("year"))
    print(f"pubmeta: {len(idents)} identifiers, {stored} from stored OpenAlex responses, "
          f"{fetched} fetched; {with_year} with a year -> {PUBMETA.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
