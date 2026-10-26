#!/usr/bin/env python3
"""Compare scView's research catalog with the hub. Offline.

Reads the rows of scView's `research/catalog-v2.tsv` in the QC-related
categories and, for each, the PMIDs it cites. Every PMID is looked up in the
hub (a record's pmid, its `papers:` and the benchmarks' pmids). Each row gets a
status:

    in-hub         every cited PMID is in the hub
    partly         some are
    new            none are: the row's literature is a lead for the hub
    no-literature  the row cites nothing

The hand-written map (exchange/scview-map.yaml) adds the hub records that back
each row, whether or not the row cites them; scview_export.py turns those into
a proposal for scView.

    python pipeline/scview_import.py [--scview FILE] [--map FILE] [--out FILE]

Writes exchange/scview-import.tsv. scView is never written to.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

import yaml

from config import DATA, ROOT

EXCHANGE = ROOT / "exchange"
SCVIEW_CATALOG = Path(os.environ.get(
    "SCVIEW_CATALOG", ROOT.parent / "scView" / "research" / "catalog-v2.tsv"))
MAP = EXCHANGE / "scview-map.yaml"
CATEGORIES = ("qc", "ambient_doublets", "quality_guardrail", "perturbation", "normalization")
PMID_RE = re.compile(r"\b\d{7,8}\b")
SOURCE_PMID_RE = re.compile(r"PMID[ :]*(\d{7,8})")
COLUMNS = ["scview_id", "category", "scview_status", "idea", "status", "pmids",
           "in_hub", "not_in_hub", "mapped_records"]


def row_pmids(row: dict) -> list[str]:
    """PMIDs a catalog row cites: its `literature` column plus `PMID n` in `sources`."""
    found = PMID_RE.findall(row.get("literature") or "")
    found += SOURCE_PMID_RE.findall(row.get("sources") or "")
    return list(dict.fromkeys(found))


def load_scview(path: Path, categories=CATEGORIES) -> list[dict]:
    with open(path, newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    return [r for r in rows if r.get("category") in categories]


def hub_pmid_index(catalog: dict) -> dict[str, list[str]]:
    """pmid -> hub record (or benchmark) ids that carry it."""
    index: dict[str, list[str]] = {}

    def add(pmid, ident):
        if pmid and ident not in index.setdefault(str(pmid), []):
            index[str(pmid)].append(ident)

    for rec in catalog["records"]:
        add(rec.get("pmid"), rec["id"])
        for paper in rec.get("papers") or []:
            if str(paper).startswith("pmid:"):
                add(paper[5:], rec["id"])
    for bench in catalog.get("benchmarks") or []:
        add(bench.get("pmid"), bench["id"])
    return index


def load_map(path: Path, record_ids: set[str]) -> dict:
    """The hand-written map; an id under `rows:` that is not a record is an error."""
    data = yaml.safe_load(Path(path).read_text()) if Path(path).exists() else {}
    data = data or {}
    rows = {str(k): list(v or []) for k, v in (data.get("rows") or {}).items()}
    bad = [f"{row}: {i}" for row, ids in rows.items() for i in ids if i not in record_ids]
    if bad:
        raise ValueError("scview map names ids that are not hub records: " + ", ".join(bad))
    return {"rows": rows, "corrections": list(data.get("corrections") or [])}


def compare(rows: list[dict], index: dict[str, list[str]], mapping: dict) -> list[dict]:
    out = []
    for row in rows:
        pmids = row_pmids(row)
        hit = [p for p in pmids if p in index]
        miss = [p for p in pmids if p not in index]
        if not pmids:
            status = "no-literature"
        elif not miss:
            status = "in-hub"
        elif hit:
            status = "partly"
        else:
            status = "new"
        out.append({
            "scview_id": row["id"],
            "category": row["category"],
            "scview_status": row.get("scview_status", ""),
            "idea": row.get("idea", ""),
            "status": status,
            "pmids": "; ".join(pmids),
            "in_hub": "; ".join(f"{p}={','.join(index[p])}" for p in hit),
            "not_in_hub": "; ".join(miss),
            "mapped_records": "; ".join(mapping["rows"].get(row["id"], [])),
        })
    return out


def write_tsv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scview", type=Path, default=SCVIEW_CATALOG)
    ap.add_argument("--catalog", type=Path, default=DATA / "catalog.json")
    ap.add_argument("--map", type=Path, default=MAP)
    ap.add_argument("--out", type=Path, default=EXCHANGE / "scview-import.tsv")
    args = ap.parse_args(argv)

    if not args.scview.exists():
        print(f"scview-import: {args.scview} not found (set SCVIEW_CATALOG)", file=sys.stderr)
        return 1
    catalog = json.loads(args.catalog.read_text())
    mapping = load_map(args.map, {r["id"] for r in catalog["records"]})
    result = compare(load_scview(args.scview), hub_pmid_index(catalog), mapping)
    write_tsv(result, args.out)

    counts: dict[str, int] = {}
    for r in result:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    unmapped = [r["scview_id"] for r in result if not r["mapped_records"]]
    missing = sorted({p for r in result for p in r["not_in_hub"].split("; ") if p})
    print(f"scview-import: {len(result)} rows -> {args.out.relative_to(ROOT)}")
    print("  " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    print(f"  {len(missing)} cited PMIDs not in the hub: {', '.join(missing) or 'none'}")
    print(f"  rows with no hub records mapped: {', '.join(unmapped) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
