#!/usr/bin/env python3
"""Stage 2c - check that every DOI and PMID names the paper the record says it does.

A resolving identifier can still be the wrong paper. The regulatory-genomics
catalog this pipeline is forked from shipped ChromBPNet pointing at "The maize
cis-regulatory landscape" and a PMID one transposed digit away from the right
one, both of which resolve without complaint. So for every record and benchmark
study with a doi or pmid:

  doi   -> Crossref (DataCite when Crossref has no record: arXiv, Zenodo)
  pmid  -> PubMed E-utilities esummary
  title -> normalised (case, punctuation, markup, accents) and compared with the
           record's cite_title; a match needs a similarity ratio >= 0.9
  both  -> must name ONE work: the PubMed record's own DOI, or failing that
           OpenAlex's id mapping, has to agree with the record's doi

Outcomes are `verified`, `mismatch` (a title that differs, ids naming two
works, or an identifier that 404s) or `unresolved` (nothing to compare, or a
service that did not answer). Only a 404 counts as broken: 429s and timeouts
are retried with backoff and, if they persist, reported as unresolved and
asked again next run. HTTP responses are cached under data/cache/.

    python pipeline/verify_citations.py [--records PATH] [--refresh] [--workers N]

Writes data/cache/verify.json (read by build.py and `make build-strict`) and
docs/citation-check.md.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

import requests

from build import identifiers, load_benchmarks, load_record_files
from config import (BENCHMARKS, CACHE, CONTACT_EMAIL, CROSSREF_API, DATACITE_API,
                    DOCS, EUTILS, MAX_WORKERS, NCBI_API_KEY, OPENALEX_API,
                    RECORDS_DIR, openalex_params, polite_params, user_agent)
from enrich import ident_key, read_openalex_work, save_openalex_work
from mdutil import cell

try:                                   # optional: faster, same scale as difflib
    from rapidfuzz.fuzz import ratio as _rf_ratio
except ImportError:                    # pragma: no cover
    _rf_ratio = None

THRESHOLD = 0.9
VERIFY_JSON = CACHE / "verify.json"
REPORT = DOCS / "citation-check.md"
CR_DIR = CACHE / "crossref"
PM_DIR = CACHE / "pubmed"


# ---------------------------------------------------------------------------
# Matching (pure functions; the tests exercise these without a network)
# ---------------------------------------------------------------------------
def norm_title(text: str) -> str:
    """A title reduced to its words: no markup, case, accents or punctuation.

    PubMed ends titles with a full stop and wraps translated ones in brackets;
    Crossref keeps <i> and <sub> tags and HTML entities; "single-cell" and
    "single cell" are the same title. None of that is a mismatch.
    """
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[\W_]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def title_ratio(a: str, b: str) -> float:
    """Similarity of two titles after normalisation, 0..1."""
    a, b = norm_title(a), norm_title(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if _rf_ratio is not None:
        return _rf_ratio(a, b) / 100.0
    return SequenceMatcher(None, a, b).ratio()


def best_ratio(cite_title: str, candidates: list[str]) -> float:
    return max((title_ratio(cite_title, c) for c in candidates if c), default=0.0)


def titles_match(cite_title: str, candidates: list[str], threshold: float = THRESHOLD) -> bool:
    return best_ratio(cite_title, candidates) >= threshold


def norm_doi(doi: str) -> str:
    doi = (doi or "").strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        doi = doi.removeprefix(prefix)
    return doi


# F1000Research and its sister platforms version a paper by DOI suffix (.1, .2),
# and PubMed indexes one version. scDblFinder is 10.12688/f1000research.73600.2
# in PubMed; a record citing .1 names the same paper, not a different one.
VERSIONED_DOI_PREFIXES = ("10.12688/",)


def same_doi(a: str, b: str) -> bool:
    a, b = norm_doi(a), norm_doi(b)
    if a == b:
        return True
    if a.startswith(VERSIONED_DOI_PREFIXES) and b.startswith(VERSIONED_DOI_PREFIXES):
        strip = lambda d: re.sub(r"\.\d+$", "", d)     # noqa: E731
        return strip(a) == strip(b)
    return False


def crossref_titles(message: dict) -> list[str]:
    """Candidate titles from a Crossref record: the title, and title + subtitle.

    Some publishers split "EmptyDrops: distinguishing cells..." into a title
    "EmptyDrops" and a subtitle, so the bare title alone would never match.
    """
    titles = [t for t in message.get("title") or [] if t]
    subs = [s for s in message.get("subtitle") or [] if s]
    out = list(titles)
    for t in titles:
        for s in subs:
            out.append(f"{t}: {s}")
    return out


def check_entry(entry: dict, doi_res: dict | None, pm_res: dict | None,
                oa_pmid: str | None = None, threshold: float = THRESHOLD) -> dict:
    """Decide one record's status from what the services returned.

    doi_res: {"state": ok|not_found|unknown, "titles": [...], "source": ...}
    pm_res:  {"state": ok|not_found|unknown, "title": str, "dois": [...]}
    oa_pmid: the PMID OpenAlex maps the doi to ("" = none, None = unknown),
             consulted only when PubMed's record carries no DOI.
    """
    doi, pmid = str(entry.get("doi") or ""), str(entry.get("pmid") or "")
    cite = entry.get("cite_title") or ""
    bad, unsure = [], []
    out = {k: entry.get(k) for k in ("kind", "id", "name", "doi", "pmid", "cite_title",
                                     "recorded_verified", "source_file")}

    if doi:
        state = (doi_res or {}).get("state", "unknown")
        if state == "not_found":
            bad.append(f"doi {doi} does not resolve (404 at Crossref and DataCite)")
        elif state != "ok":
            unsure.append("Crossref did not answer for the doi (retry later)")
        else:
            titles = doi_res.get("titles") or []
            out["doi_title"] = titles[0] if titles else ""
            out["doi_source"] = doi_res.get("source", "")
            if not titles:
                unsure.append("the doi's registry record has no title")
            elif cite:
                r = best_ratio(cite, titles)
                out["doi_ratio"] = round(r, 3)
                if r < threshold:
                    bad.append(f"doi title differs from cite_title (similarity {r:.2f})")
    if pmid:
        state = (pm_res or {}).get("state", "unknown")
        if state == "not_found":
            bad.append(f"pmid {pmid} does not exist in PubMed")
        elif state != "ok":
            unsure.append("PubMed did not answer for the pmid (retry later)")
        else:
            out["pmid_title"] = pm_res.get("title", "")
            if cite and out["pmid_title"]:
                r = best_ratio(cite, [out["pmid_title"]])
                out["pmid_ratio"] = round(r, 3)
                if r < threshold:
                    bad.append(f"PubMed title differs from cite_title (similarity {r:.2f})")
            if doi:
                dois = pm_res.get("dois") or []
                if dois:
                    out["ids_agree"] = any(same_doi(doi, d) for d in dois)
                    if not out["ids_agree"]:
                        bad.append(f"doi and pmid name different works "
                                   f"(PubMed gives doi {dois[0]} for pmid {pmid})")
                elif oa_pmid:
                    out["ids_agree"] = oa_pmid == pmid
                    if not out["ids_agree"]:
                        bad.append(f"doi and pmid name different works "
                                   f"(OpenAlex maps the doi to pmid {oa_pmid})")
                else:
                    unsure.append("could not cross-check doi against pmid "
                                  "(no DOI in PubMed, none mapped by OpenAlex)")
    if not cite:
        unsure.append("no cite_title to compare against")

    out["status"] = "mismatch" if bad else ("unresolved" if unsure else "verified")
    out["reasons"] = bad + unsure
    return out


# ---------------------------------------------------------------------------
# Network, cached and polite
# ---------------------------------------------------------------------------
class RateLimiter:
    """At most one request per `interval` seconds, across threads."""

    def __init__(self, interval: float):
        self.interval, self.lock, self.next = interval, threading.Lock(), 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            delay = self.next - now
            self.next = max(now, self.next) + self.interval
        if delay > 0:
            time.sleep(delay)


def polite_get(session: requests.Session, url: str, limiter: RateLimiter,
               params: dict | None = None, attempts: int = 5) -> tuple[str, dict | None]:
    """("ok", json) | ("not_found", None) | ("unknown", None).

    429 and 5xx are transient, honouring Retry-After; an early link checker in
    the upstream catalog reported 151 broken DOIs that were all rate-limited
    retries of good ones. Only a 404 means the thing does not exist.
    """
    delay = 1.0
    for _ in range(attempts):
        limiter.wait()
        try:
            r = session.get(url, params=params, timeout=30)
        except requests.RequestException:
            time.sleep(delay)
            delay *= 2
            continue
        if r.status_code == 200:
            try:
                return "ok", r.json()
            except ValueError:
                return "unknown", None
        if r.status_code == 404:
            return "not_found", None
        try:
            wait = float(r.headers.get("Retry-After") or delay)
        except ValueError:
            wait = delay
        time.sleep(min(wait, 30))
        delay *= 2
    return "unknown", None


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def _cached(path: Path, refresh: bool) -> dict | None:
    if refresh or not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except ValueError:
        return None


def _store(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True))


def fetch_doi(session: requests.Session, doi: str, limiter: RateLimiter,
              refresh: bool = False) -> dict:
    """Titles for a DOI from Crossref, falling back to DataCite on a Crossref 404.

    Only definite answers (200, 404) are cached; an unanswered request is asked
    again next run rather than frozen as broken.
    """
    path = CR_DIR / f"{_safe(norm_doi(doi))}.json"
    hit = _cached(path, refresh)
    if hit is not None:
        return hit
    state, data = polite_get(session, CROSSREF_API + doi, limiter, polite_params())
    if state == "ok":
        msg = (data or {}).get("message") or {}
        res = {"state": "ok", "source": "crossref", "titles": crossref_titles(msg),
               "container": (msg.get("container-title") or [""])[0], "type": msg.get("type", "")}
        _store(path, res)
        return res
    if state == "not_found":
        # arXiv, Zenodo, figshare and Bioconductor DOIs are DataCite's, and
        # Crossref 404s on them. That is not a broken DOI.
        dstate, ddata = polite_get(session, DATACITE_API + doi, limiter)
        if dstate == "ok":
            attrs = ((ddata or {}).get("data") or {}).get("attributes") or {}
            res = {"state": "ok", "source": "datacite",
                   "titles": [t.get("title") for t in attrs.get("titles") or [] if t.get("title")],
                   "container": attrs.get("publisher") or "", "type": (attrs.get("types") or {}).get("resourceTypeGeneral", "")}
            _store(path, res)
            return res
        if dstate == "not_found":
            res = {"state": "not_found"}
            _store(path, res)
            return res
    return {"state": "unknown"}


def fetch_pubmed(session: requests.Session, pmids: list[str], limiter: RateLimiter,
                 refresh: bool = False) -> dict[str, dict]:
    """pmid -> {state, title, dois}, from esummary in batches of up to 100."""
    out: dict[str, dict] = {}
    todo = []
    for p in dict.fromkeys(pmids):
        hit = _cached(PM_DIR / f"{p}.json", refresh)
        if hit is not None:
            out[p] = hit
        else:
            todo.append(p)
    params = {"db": "pubmed", "retmode": "json", "tool": "awesome-single-cell-qc"}
    if CONTACT_EMAIL:
        params["email"] = CONTACT_EMAIL
    if NCBI_API_KEY:
        params["api_key"] = NCBI_API_KEY
    for i in range(0, len(todo), 100):
        batch = todo[i:i + 100]
        state, data = polite_get(session, EUTILS + "esummary.fcgi", limiter,
                                 {**params, "id": ",".join(batch)})
        result = (data or {}).get("result") or {}
        for p in batch:
            if state != "ok":
                out[p] = {"state": "unknown"}
                continue
            doc = result.get(p)
            if not doc or doc.get("error"):
                res = {"state": "not_found"}
            else:
                res = {"state": "ok", "title": doc.get("title", ""),
                       "source": doc.get("fulljournalname") or doc.get("source", ""),
                       "pubdate": doc.get("pubdate", ""),
                       "dois": [a.get("value") for a in doc.get("articleids") or []
                                if a.get("idtype") == "doi" and a.get("value")]}
            _store(PM_DIR / f"{p}.json", res)
            out[p] = res
    return out


def openalex_pmid(session: requests.Session, doi: str, limiter: RateLimiter) -> str | None:
    """The PMID OpenAlex maps a DOI to: digits, "" for none, None if unknown."""
    key = ident_key(f"doi:{doi}")
    work = read_openalex_work(key)
    if not work:
        state, data = polite_get(session, OPENALEX_API, limiter,
                                 openalex_params({"filter": f"doi:{doi}"}))
        if state != "ok":
            return None
        if not (data or {}).get("results"):
            return ""
        save_openalex_work(key, data)
        work = data["results"][0]
    return ((work.get("ids") or {}).get("pmid") or "").rstrip("/").split("/")[-1]


# ---------------------------------------------------------------------------
def collect_entries(records_path: Path, benchmarks_path: Path) -> tuple[list[dict], int]:
    """Everything with a doi or pmid, records and benchmarks alike; plus a count of the rest."""
    files, _ = load_record_files(records_path)
    benches, _ = load_benchmarks(benchmarks_path)
    entries, skipped = [], 0
    for fname, recs in files:
        for r in recs:
            if not isinstance(r, dict) or not r.get("id"):
                continue
            if not identifiers(r):
                skipped += 1
                continue
            entries.append({"key": f"record:{r['id']}", "kind": "record", "id": r["id"],
                            "name": r.get("name", ""), "doi": str(r.get("doi") or "").strip(),
                            "pmid": str(r.get("pmid") or "").strip(),
                            "cite_title": r.get("cite_title") or "",
                            "recorded_verified": r.get("verified") is True,
                            "source_file": fname})
    for b in benches:
        if not identifiers(b):
            skipped += 1
            continue
        entries.append({"key": f"benchmark:{b['id']}", "kind": "benchmark", "id": b["id"],
                        "name": b.get("name", ""), "doi": str(b.get("doi") or "").strip(),
                        "pmid": str(b.get("pmid") or "").strip(),
                        "cite_title": b.get("cite_title") or "",
                        "recorded_verified": b.get("verified") is True,
                        "source_file": "benchmarks.yaml"})
    return entries, skipped


def render_report(results: list[dict], skipped: int, today: str) -> str:
    by = {s: [r for r in results if r["status"] == s] for s in ("mismatch", "unresolved", "verified")}
    flips_up = [r for r in by["verified"] if not r.get("recorded_verified")]
    flips_down = [r for r in results if r.get("recorded_verified") and r["status"] != "verified"]
    out = ["# Citation check", "",
           f"GENERATED by `make verify` on {today}; do not edit. Each DOI is fetched from "
           "Crossref (DataCite when Crossref has none) and each PMID from PubMed; the "
           f"returned title must match `cite_title` with a similarity of at least {THRESHOLD} "
           "after normalising case, punctuation, markup and accents, and a doi and a pmid on "
           "the same record must name one work.", "",
           f"- **{len(by['verified'])} verified**, **{len(by['mismatch'])} mismatched**, "
           f"**{len(by['unresolved'])} unresolved**; {skipped} entries have no doi or pmid "
           "and are not checked.",
           f"- {len(flips_down)} say `verified: true` but did not verify here; "
           f"{len(flips_up)} verified here but say `verified: false`.", ""]

    def ident(r):
        bits = []
        if r.get("doi"):
            bits.append(f"[doi:{cell(r['doi'])}](https://doi.org/{r['doi']})")
        if r.get("pmid"):
            bits.append(f"[pmid:{r['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/)")
        return "<br>".join(bits)

    out += ["## Mismatched", ""]
    if by["mismatch"]:
        out += ["| Entry | Identifiers | Problem | Fetched title | cite_title |",
                "| --- | --- | --- | --- | --- |"]
        for r in by["mismatch"]:
            fetched = r.get("doi_title") or r.get("pmid_title") or ""
            out.append(f"| {r['kind']} `{r['id']}` ({cell(r.get('source_file'))}) | {ident(r)} | "
                       f"{cell('; '.join(r['reasons']))} | {cell(fetched, 120)} | "
                       f"{cell(r.get('cite_title'), 120)} |")
    else:
        out.append("None.")
    out += ["", "## Unresolved", ""]
    if by["unresolved"]:
        out += ["| Entry | Identifiers | Why |", "| --- | --- | --- |"]
        for r in by["unresolved"]:
            out.append(f"| {r['kind']} `{r['id']}` ({cell(r.get('source_file'))}) | {ident(r)} | "
                       f"{cell('; '.join(r['reasons']))} |")
    else:
        out.append("None.")
    out += ["", "## Verified", ""]
    if by["verified"]:
        out += ["| Entry | Identifiers | Similarity | Recorded `verified` |",
                "| --- | --- | ---: | --- |"]
        for r in by["verified"]:
            ratios = [str(r[k]) for k in ("doi_ratio", "pmid_ratio") if k in r]
            out.append(f"| {r['kind']} `{r['id']}` | {ident(r)} | {' / '.join(ratios)} | "
                       f"{'true' if r.get('recorded_verified') else '**false**'} |")
    else:
        out.append("None.")
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--records", type=Path,
                    default=Path(os.environ.get("RECORDS_DIR") or RECORDS_DIR))
    ap.add_argument("--benchmarks", type=Path,
                    default=Path(os.environ.get("BENCHMARKS_FILE") or BENCHMARKS))
    ap.add_argument("--refresh", action="store_true", help="ignore cached responses")
    ap.add_argument("--workers", type=int, default=3,
                    help=f"parallel Crossref requests (capped at {MAX_WORKERS})")
    ap.add_argument("--report", type=Path, default=REPORT)
    ap.add_argument("--fail-on-mismatch", action="store_true")
    args = ap.parse_args(argv)

    entries, skipped = collect_entries(args.records, args.benchmarks)
    print(f"Checking {len(entries)} entries ({skipped} without a doi or pmid skipped)")
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent(), "Accept": "application/json"})
    cr_limit = RateLimiter(0.2)
    pm_limit = RateLimiter(0.11 if NCBI_API_KEY else 0.35)
    oa_limit = RateLimiter(0.11)

    dois = list(dict.fromkeys(e["doi"] for e in entries if e["doi"]))
    workers = max(1, min(args.workers, MAX_WORKERS))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        doi_res = dict(zip(dois, pool.map(
            lambda d: fetch_doi(session, d, cr_limit, args.refresh), dois)))
    pm_res = fetch_pubmed(session, [e["pmid"] for e in entries if e["pmid"]], pm_limit, args.refresh)

    results = []
    for e in entries:
        pm = pm_res.get(e["pmid"]) if e["pmid"] else None
        oa = None
        if e["doi"] and pm and pm.get("state") == "ok" and not pm.get("dois"):
            oa = openalex_pmid(session, e["doi"], oa_limit)
        results.append(check_entry(e, doi_res.get(e["doi"]) if e["doi"] else None, pm, oa))
    results.sort(key=lambda r: (r["kind"], r["id"]))

    today = date.today().isoformat()
    _store(VERIFY_JSON, {"generated": today, "threshold": THRESHOLD,
                         "entries": {f"{r['kind']}:{r['id']}": r for r in results}})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(results, skipped, today))
    n = {s: sum(1 for r in results if r["status"] == s) for s in ("verified", "mismatch", "unresolved")}
    print(f"  verified {n['verified']}, mismatch {n['mismatch']}, unresolved {n['unresolved']}")
    for r in results:
        if r["status"] != "verified":
            print(f"  {r['status']:10s} {r['kind']} {r['id']}: {'; '.join(r['reasons'])}")
    print(f"-> {VERIFY_JSON.name}, {args.report.name}")
    return 1 if args.fail_on_mismatch and n["mismatch"] else 0


if __name__ == "__main__":
    sys.exit(main())
