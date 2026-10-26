"""Title normalisation, matching and the citation check, with no network.

Every HTTP call goes to a fake session, so these run offline and fast, and the
retry/backoff paths can be exercised without waiting for a real 429.
"""
import json
from pathlib import Path

import pytest
import yaml

import build
import config
import enrich
import verify_citations as vc

FIXTURES = Path(__file__).parent / "fixtures"
RECORDS_SEED = FIXTURES / "records_seed.yaml"
BENCH_SEED = FIXTURES / "benchmarks_seed.yaml"


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code, self.body, self.headers = status, body, headers or {}

    @property
    def text(self):
        return json.dumps(self.body) if self.body is not None else ""

    def json(self):
        if self.body is None:
            raise ValueError("no body")
        return self.body


class FakeSession:
    """Routes GETs to a handler(url, params) -> FakeResponse, and records them."""

    def __init__(self, handler):
        self.handler, self.calls, self.headers = handler, [], {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        return self.handler(url, params or {})


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """No sleeping, and every cache under tmp_path, never data/cache."""
    monkeypatch.setattr(vc.time, "sleep", lambda s: None)
    monkeypatch.setattr(vc, "CR_DIR", tmp_path / "crossref")
    monkeypatch.setattr(vc, "PM_DIR", tmp_path / "pubmed")
    monkeypatch.setattr(vc, "VERIFY_JSON", tmp_path / "verify.json")
    monkeypatch.setattr(enrich, "OA_DIR", tmp_path / "openalex")


NOW = vc.RateLimiter(0)


# ---------------------------------------------------------------------------
# normalisation and matching
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("a,b", [
    ("EmptyDrops: distinguishing cells from empty droplets.",
     "emptydrops distinguishing cells from empty droplets"),
    ("Single-cell RNA-seq", "single cell rna seq"),
    ("<i>De novo</i> discovery &amp; more", "de novo discovery more"),
    ("[Analyse des cellules uniques].", "analyse des cellules uniques"),
    ("Café naïve", "cafe naive"),
])
def test_norm_title(a, b):
    assert vc.norm_title(a) == b


def test_identical_titles_after_normalisation_score_one():
    assert vc.title_ratio("SoupX removes ambient RNA contamination.",
                          "soupx removes ambient rna contamination") == 1.0


def test_a_different_paper_fails_the_threshold():
    """The upstream catalog's real case: a resolving DOI for the wrong paper."""
    assert not vc.titles_match("ChromBPNet: bias factorized, base-resolution deep learning models",
                               ["The maize cis-regulatory landscape"])


def test_a_one_word_difference_in_a_long_title_still_matches():
    cite = "Doublet identification in single-cell sequencing data using scDblFinder"
    assert vc.titles_match(cite, ["Doublet identification in single-cell sequencing datasets using scDblFinder"])


def test_a_short_title_change_is_not_waved_through():
    assert not vc.titles_match("CellBender", ["CellRanger"])


def test_empty_titles_never_match():
    assert vc.title_ratio("", "anything") == 0.0
    assert not vc.titles_match("A title", [])


def test_crossref_title_plus_subtitle_matches_a_full_title():
    msg = {"title": ["EmptyDrops"],
           "subtitle": ["distinguishing cells from empty droplets in droplet-based "
                        "single-cell RNA sequencing data"]}
    cite = ("EmptyDrops: distinguishing cells from empty droplets in droplet-based "
            "single-cell RNA sequencing data")
    assert not vc.titles_match(cite, msg["title"])
    assert vc.titles_match(cite, vc.crossref_titles(msg))


@pytest.mark.parametrize("a,b,same", [
    ("10.1186/S13059-019-1662-Y", "10.1186/s13059-019-1662-y", True),
    ("https://doi.org/10.1093/gigascience/giaa151", "10.1093/gigascience/giaa151", True),
    ("10.12688/f1000research.73600.1", "10.12688/f1000research.73600.2", True),
    ("10.1101/2023.03.17.533005", "10.1101/2023.03.17.533006", False),
    ("10.1093/bioinformatics/btad481", "10.1093/bioinformatics/btad461", False),
])
def test_same_doi(a, b, same):
    assert vc.same_doi(a, b) is same


# ---------------------------------------------------------------------------
# deciding a record's status
# ---------------------------------------------------------------------------
ENTRY = {"kind": "record", "id": "demuxmix", "name": "demuxmix",
         "doi": "10.1093/bioinformatics/btad481", "pmid": "37527018",
         "cite_title": "demuxmix: demultiplexing oligonucleotide-barcoded single-cell RNA "
                       "sequencing data with regression mixture models"}
CR_OK = {"state": "ok", "source": "crossref", "titles": [ENTRY["cite_title"]]}
PM_OK = {"state": "ok", "title": ENTRY["cite_title"] + ".",
         "dois": ["10.1093/bioinformatics/btad481"]}


def test_verified_when_both_titles_match_and_ids_agree():
    r = vc.check_entry(ENTRY, CR_OK, PM_OK)
    assert r["status"] == "verified" and r["ids_agree"] is True and r["reasons"] == []


def test_a_title_that_differs_is_a_mismatch():
    r = vc.check_entry(ENTRY, {**CR_OK, "titles": ["AlphaPeptStats: an open-source Python package"]}, PM_OK)
    assert r["status"] == "mismatch" and "doi title differs" in r["reasons"][0]


def test_a_pmid_for_a_different_work_is_a_mismatch():
    """A transposed digit: 37527012 is a real PMID, for a proteomics paper."""
    pm = {"state": "ok", "title": ENTRY["cite_title"], "dois": ["10.1093/bioinformatics/btad461"]}
    r = vc.check_entry(ENTRY, CR_OK, pm)
    assert r["status"] == "mismatch" and r["ids_agree"] is False
    assert any("different works" in x for x in r["reasons"])


def test_a_404_is_a_mismatch_but_no_answer_is_unresolved():
    assert vc.check_entry(ENTRY, {"state": "not_found"}, PM_OK)["status"] == "mismatch"
    assert vc.check_entry(ENTRY, {"state": "unknown"}, PM_OK)["status"] == "unresolved"
    assert vc.check_entry(ENTRY, CR_OK, {"state": "not_found"})["status"] == "mismatch"
    assert vc.check_entry(ENTRY, CR_OK, {"state": "unknown"})["status"] == "unresolved"


def test_openalex_cross_checks_when_pubmed_has_no_doi():
    pm = {**PM_OK, "dois": []}
    assert vc.check_entry(ENTRY, CR_OK, pm, oa_pmid="37527018")["status"] == "verified"
    assert vc.check_entry(ENTRY, CR_OK, pm, oa_pmid="11111111")["status"] == "mismatch"
    assert vc.check_entry(ENTRY, CR_OK, pm, oa_pmid=None)["status"] == "unresolved"


def test_without_a_cite_title_nothing_can_be_verified():
    r = vc.check_entry({**ENTRY, "cite_title": ""}, CR_OK, PM_OK)
    assert r["status"] == "unresolved" and "no cite_title" in r["reasons"][-1]


def test_doi_only_and_pmid_only_records():
    assert vc.check_entry({**ENTRY, "pmid": ""}, CR_OK, None)["status"] == "verified"
    assert vc.check_entry({**ENTRY, "doi": ""}, None, PM_OK)["status"] == "verified"


# ---------------------------------------------------------------------------
# network layer, mocked
# ---------------------------------------------------------------------------
def test_crossref_404_falls_back_to_datacite(tmp_path):
    def handler(url, params):
        if url.startswith(config.CROSSREF_API):
            return FakeResponse(404)
        return FakeResponse(200, {"data": {"attributes": {
            "titles": [{"title": "A preprint on arXiv"}], "publisher": "arXiv"}}})
    res = vc.fetch_doi(FakeSession(handler), "10.48550/arXiv.2301.00001", NOW)
    assert res["state"] == "ok" and res["source"] == "datacite"
    assert res["titles"] == ["A preprint on arXiv"]


def test_a_404_at_both_registries_is_broken_and_cached(tmp_path):
    s = FakeSession(lambda url, params: FakeResponse(404))
    assert vc.fetch_doi(s, "10.9999/nope", NOW)["state"] == "not_found"
    n = len(s.calls)
    assert vc.fetch_doi(s, "10.9999/nope", NOW)["state"] == "not_found"
    assert len(s.calls) == n                          # second answer from the cache


def test_rate_limiting_is_retried_not_reported_broken():
    replies = [FakeResponse(429, headers={"Retry-After": "1"}),
               FakeResponse(503),
               FakeResponse(200, {"message": {"title": ["Recovered after backoff"]}})]
    s = FakeSession(lambda url, params: replies.pop(0))
    res = vc.fetch_doi(s, "10.1000/flaky", NOW)
    assert res["state"] == "ok" and res["titles"] == ["Recovered after backoff"]
    assert len(s.calls) == 3


def test_persistent_429_is_unknown_and_not_cached(tmp_path):
    s = FakeSession(lambda url, params: FakeResponse(429))
    assert vc.fetch_doi(s, "10.1000/busy", NOW)["state"] == "unknown"
    assert not (tmp_path / "crossref").exists() or not list((tmp_path / "crossref").iterdir())


def test_pubmed_is_fetched_in_one_batch_and_parses_dois():
    def handler(url, params):
        ids = params["id"].split(",")
        result = {"uids": ids}
        for p in ids:
            result[p] = ({"uid": p, "error": "cannot get document summary"} if p == "1"
                         else {"uid": p, "title": f"Paper {p}.",
                               "articleids": [{"idtype": "pubmed", "value": p},
                                              {"idtype": "doi", "value": f"10.1000/{p}"}]})
        return FakeResponse(200, {"result": result})
    s = FakeSession(handler)
    out = vc.fetch_pubmed(s, ["30902100", "1", "30902100"], NOW)
    assert len(s.calls) == 1 and s.calls[0][1]["id"] == "30902100,1"
    assert out["30902100"]["dois"] == ["10.1000/30902100"]
    assert out["1"]["state"] == "not_found"


def test_openalex_failures_are_never_cached_as_zero():
    cache = {}
    s = FakeSession(lambda url, params: FakeResponse(200, {"results": []}))
    assert enrich.openalex_lookup(s, "doi:10.1000/unindexed", cache) == (None, {})
    assert cache == {}
    s = FakeSession(lambda url, params: FakeResponse(200, {"results": [
        {"cited_by_count": 42, "title": "T", "publication_year": 2020}]}))
    count, _ = enrich.openalex_lookup(s, "doi:10.1000/indexed", cache)
    assert count == 42 and cache == {"doi_10.1000_indexed": 42}
    assert enrich.read_openalex_work("doi_10.1000_indexed")["cited_by_count"] == 42


def test_enrich_collects_identifiers_and_github_slugs_from_records():
    idents, slugs = enrich.collect(RECORDS_SEED, BENCH_SEED)
    assert "doi:10.1186/s13059-019-1662-y" in idents and "pmid:30902100" in idents
    assert "doi:10.1016/j.cels.2020.11.008" in idents         # benchmarks too
    assert "MarioniLab/DropletUtils" in slugs and len(slugs) == 6


# ---------------------------------------------------------------------------
# end to end: verify_citations.main over the fixtures, then build
# ---------------------------------------------------------------------------
def fixture_handler():
    recs = yaml.safe_load(RECORDS_SEED.read_text())["records"]
    recs += yaml.safe_load(BENCH_SEED.read_text())["benchmarks"]
    by_doi = {r["doi"]: r for r in recs}
    by_pmid = {str(r["pmid"]): r for r in recs}

    def handler(url, params):
        if url.startswith(config.CROSSREF_API):
            doi = url[len(config.CROSSREF_API):]
            r = by_doi.get(doi)
            if not r:
                return FakeResponse(404)
            # SoupX's DOI comes back as a different paper: the check must catch it.
            title = "An unrelated paper about plants" if r["id"] == "soupx" else r["cite_title"]
            return FakeResponse(200, {"message": {"title": [title]}})
        if url.startswith(config.EUTILS):
            ids = params["id"].split(",")
            result = {"uids": ids}
            for p in ids:
                r = by_pmid[p]
                result[p] = {"title": r["cite_title"] + ".",
                             "articleids": [{"idtype": "doi", "value": r["doi"]}]}
            return FakeResponse(200, {"result": result})
        return FakeResponse(404)
    return handler


def test_verify_main_writes_verify_json_and_the_report(monkeypatch, tmp_path):
    monkeypatch.setattr(vc.requests, "Session", lambda: FakeSession(fixture_handler()))
    report = tmp_path / "citation-check.md"
    rc = vc.main(["--records", str(RECORDS_SEED), "--benchmarks", str(BENCH_SEED),
                  "--report", str(report), "--workers", "9"])
    assert rc == 0
    entries = json.loads((tmp_path / "verify.json").read_text())["entries"]
    assert len(entries) == 8
    assert entries["record:soupx"]["status"] == "mismatch"
    assert all(e["status"] == "verified" for k, e in entries.items() if k != "record:soupx")
    md = report.read_text()
    for heading in ("## Mismatched", "## Unresolved", "## Verified"):
        assert heading in md
    assert "soupx" in md.split("## Unresolved")[0]
    assert "\u2014" not in md

    # build reads the result, and build-strict refuses the contradicted record
    catalog, errors, _ = build.build_catalog(RECORDS_SEED, BENCH_SEED, tmp_path)
    assert not errors
    rows = {r["id"]: r for r in catalog["records"]}
    assert rows["soupx"]["citation_check"] == "mismatch"
    assert rows["emptydrops"]["citation_check"] == "verified"
    fails = build.strict_failures(catalog, build.load_verify(tmp_path))
    assert len(fails) == 1 and fails[0].startswith("soupx")


def test_verify_never_runs_more_than_the_worker_cap(monkeypatch, tmp_path):
    seen = {}
    real = vc.ThreadPoolExecutor

    def capped(max_workers):
        seen["n"] = max_workers
        return real(max_workers=max_workers)
    monkeypatch.setattr(vc, "ThreadPoolExecutor", capped)
    monkeypatch.setattr(vc.requests, "Session", lambda: FakeSession(fixture_handler()))
    vc.main(["--records", str(RECORDS_SEED), "--benchmarks", str(BENCH_SEED),
             "--report", str(tmp_path / "r.md"), "--workers", "16"])
    assert seen["n"] == config.MAX_WORKERS == 4
