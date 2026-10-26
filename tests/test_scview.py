"""scView exchange: PMID matching, row status, the map check, the proposal."""
from pathlib import Path

import pytest

import scview_export
import scview_import

CATALOG = {
    "records": [
        {"id": "soupx", "name": "SoupX", "tier": "standard", "pmid": "33367645", "verified": True,
         "summary": "Subtracts the soup", "papers": ["pmid:11111111"], "benchmark_refs": []},
        {"id": "decontx", "name": "DecontX", "tier": "benchmarked-sota", "pmid": "32138770",
         "verified": True, "summary": "Bayesian decontamination", "papers": [],
         "benchmark_refs": [{"id": "janssen", "name": "Janssen 2023"}]},
        {"id": "knee", "name": "Knee calling", "tier": "standard", "url": "https://x.org",
         "summary": "Barcode-rank knee", "papers": [], "benchmark_refs": []},
    ],
    "benchmarks": [{"id": "janssen", "pmid": "37337297"}],
}
HEADER = "id\tidea\tcategory\tscview_status\tliterature\tsources\n"


def scview_tsv(tmp_path: Path) -> Path:
    path = tmp_path / "catalog-v2.tsv"
    path.write_text(HEADER
                    + "C066\tAmbient\tambient_doublets\tmissing\t33367645; 37337297\tx\n"
                    + "C091\tNorm\tnormalization\tmissing\t32138770; 99999999\tPMID 88888888\n"
                    + "C054\tLedger\tquality_guardrail\tmissing\t40463689\t\n"
                    + "N22\tSeq metrics\tqc\tmissing\t\t\n"
                    + "C008\tPalette\tinteraction_ux\tpartial\t21850730\t\n")
    return path


def test_pmids_come_from_literature_and_sources_once_each():
    row = {"literature": "31948481; 33257685", "sources": "x.tsv:43 31948481 | PMID 33257685 | PMID 29121214"}
    assert scview_import.row_pmids(row) == ["31948481", "33257685", "29121214"]


def test_only_qc_categories_are_read(tmp_path):
    ids = [r["id"] for r in scview_import.load_scview(scview_tsv(tmp_path))]
    assert ids == ["C066", "C091", "C054", "N22"]


def test_hub_index_covers_records_papers_and_benchmarks():
    index = scview_import.hub_pmid_index(CATALOG)
    assert index["33367645"] == ["soupx"]
    assert index["11111111"] == ["soupx"]
    assert index["37337297"] == ["janssen"]


def test_status_per_row(tmp_path):
    mapping = {"rows": {"C066": ["soupx"]}, "corrections": []}
    rows = scview_import.compare(scview_import.load_scview(scview_tsv(tmp_path)),
                                 scview_import.hub_pmid_index(CATALOG), mapping)
    status = {r["scview_id"]: r["status"] for r in rows}
    assert status == {"C066": "in-hub", "C091": "partly", "C054": "new", "N22": "no-literature"}
    c091 = next(r for r in rows if r["scview_id"] == "C091")
    assert c091["not_in_hub"] == "99999999; 88888888"
    assert c091["in_hub"] == "32138770=decontx"
    assert rows[0]["mapped_records"] == "soupx"


def test_map_with_an_unknown_record_id_fails(tmp_path):
    path = tmp_path / "map.yaml"
    path.write_text("rows:\n  C066: [soupx, no-such-record]\n")
    with pytest.raises(ValueError, match="C066: no-such-record"):
        scview_import.load_map(path, {"soupx"})


def test_proposal_skips_cited_records_and_ranks_by_tier(tmp_path):
    rows = scview_import.load_scview(scview_tsv(tmp_path))
    records = {r["id"]: r for r in CATALOG["records"]}
    mapping = {"rows": {"C066": ["soupx", "knee", "decontx"], "N22": ["knee"]},
               "corrections": [{"row": "C051", "pmid": "34594043", "problem": "is Milo",
                                "fix": "cite 36005887"}]}
    text = scview_export.render(rows, mapping, records, "2026-10-25")
    c066 = text.split("### C066")[1].split("###")[0]
    assert "SoupX" not in c066                      # the row already cites it
    assert c066.index("Knee calling") < c066.index("DecontX")   # schema tier order
    assert "Benchmarked in: Janssen 2023." in c066
    assert "(standard; https://x.org)" in c066
    assert "1. **C051** (cites 34594043): is Milo. Fix: cite 36005887." in text
    assert "2 do not (C091, C054)" in text
    assert "—" not in text
