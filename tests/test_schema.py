"""Record validation against curation/schema.yaml, and the build around it.

The schema is the single source of truth for every enumerated value, so these
tests read the vocabulary back from schema.yaml rather than restating it: a
value the schema drops must start failing here without anyone editing a test.
"""
from pathlib import Path

import pytest
import yaml

import build
import config

FIXTURES = Path(__file__).parent / "fixtures"
RECORDS_SEED = FIXTURES / "records_seed.yaml"
BENCH_SEED = FIXTURES / "benchmarks_seed.yaml"


def record(**over) -> dict:
    """A minimal valid record, with overrides."""
    base = {"id": "toy-tool", "name": "ToyTool", "kind": "tool", "layer": "core",
            "categories": ["doublets"], "side": "subtractive", "tier": "standard",
            "summary": "Flags doublets in a toy way"}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def write(dirpath: Path, name: str, records: list | None, key: str = "records") -> Path:
    path = dirpath / name
    path.write_text(yaml.safe_dump({key: records}, sort_keys=False) if records is not None else "")
    return path


def errors_for(rec: dict, bench=frozenset()) -> list[str]:
    errs, _ = build.validate_record(rec, "t.yaml record 1", set(bench))
    return errs


def warnings_for(rec: dict) -> list[str]:
    _, warns = build.validate_record(rec, "t.yaml record 1", set())
    return warns


# ---------------------------------------------------------------------------
# the vocabulary comes from schema.yaml
# ---------------------------------------------------------------------------
def test_vocabulary_is_read_from_schema_yaml():
    schema = yaml.safe_load(config.SCHEMA_PATH.read_text())
    assert list(config.TIERS) == list(schema["tiers"])
    assert list(config.KINDS) == list(schema["kinds"])
    assert list(config.SIDES) == list(schema["sides"])
    assert list(config.LAYERS) == list(schema["layers"])
    assert list(config.REQUIRES) == list(schema["requires"])
    assert list(config.GAIN_SOURCES) == list(schema["gain_sources"])
    assert config.CATEGORY_KEYS == list(schema["categories"])
    assert config.REQUIRED == schema["required"]


def test_every_category_names_a_known_layer():
    for key, layer in config.CATEGORY_LAYER.items():
        assert layer in config.LAYERS, key


def test_language_enum_is_parsed_from_the_field_description():
    assert "R" in config.LANGUAGES and "Python" in config.LANGUAGES
    assert "multiple" in config.LANGUAGES


def test_every_fixture_value_is_in_the_vocabulary():
    recs = yaml.safe_load(RECORDS_SEED.read_text())["records"]
    assert len(recs) == 6
    for r in recs:
        assert r["kind"] in config.KINDS and r["tier"] in config.TIERS
        assert r["side"] in config.SIDES and r["layer"] in config.LAYERS
        assert all(c in config.CATEGORY_KEYS for c in r["categories"])
        assert all(q in config.REQUIRES for q in r.get("requires") or [])


# ---------------------------------------------------------------------------
# fixtures and empty inputs build cleanly
# ---------------------------------------------------------------------------
def test_fixture_records_build_without_errors_or_warnings(tmp_path):
    catalog, errors, warnings = build.build_catalog(RECORDS_SEED, BENCH_SEED, tmp_path)
    assert errors == [] and warnings == []
    assert catalog["meta"]["count"] == 6
    assert {r["id"] for r in catalog["records"]} == {
        "emptydrops", "cellbender", "soupx", "scdblfinder", "demuxmix", "dreamlet"}
    assert catalog["meta"]["by_layer"] == {"core": 5, "adjacent": 1}
    assert sum(catalog["meta"]["by_tier"].values()) == 6


def test_an_empty_records_dir_builds_zero_records(tmp_path):
    (tmp_path / "records").mkdir()
    catalog, errors, _ = build.build_catalog(tmp_path / "records", tmp_path / "none.yaml", tmp_path)
    assert errors == []
    assert catalog["meta"]["count"] == 0 and catalog["records"] == []


def test_an_empty_file_and_an_empty_list_are_zero_records(tmp_path):
    write(tmp_path, "a.yaml", None)
    write(tmp_path, "b.yaml", [])
    catalog, errors, _ = build.build_catalog(tmp_path, tmp_path / "none.yaml", tmp_path)
    assert errors == [] and catalog["meta"]["count"] == 0


def test_a_file_without_the_records_key_is_an_error(tmp_path):
    write(tmp_path, "a.yaml", [record()], key="recrods")
    _, errors, _ = build.build_catalog(tmp_path, tmp_path / "none.yaml", tmp_path)
    assert any("records:" in e and "a.yaml" in e for e in errors)


def test_invalid_yaml_names_the_file(tmp_path):
    (tmp_path / "bad.yaml").write_text("records:\n  - id: [unclosed\n")
    _, errors, _ = build.build_catalog(tmp_path, tmp_path / "none.yaml", tmp_path)
    assert any("bad.yaml" in e and "YAML" in e for e in errors)


# ---------------------------------------------------------------------------
# validation rules
# ---------------------------------------------------------------------------
def test_a_minimal_record_is_valid():
    assert errors_for(record()) == []


@pytest.mark.parametrize("field", config.REQUIRED)
def test_each_required_field_is_enforced(field):
    rec = record()
    rec.pop(field)
    assert any(f"missing required field '{field}'" in e for e in errors_for(rec))


@pytest.mark.parametrize("field,value", [
    ("kind", "software"), ("layer", "periphery"), ("side", "additve"),
    ("tier", "sota"), ("gain_source", "authors"), ("language", "Julia"),
])
def test_unknown_enumerated_values_are_rejected(field, value):
    errs = errors_for(record(**{field: value}))
    assert any(f"{field} '{value}'" in e for e in errs), errs


def test_unknown_category_and_requires_are_rejected():
    errs = errors_for(record(categories=["doublets", "vibes"], requires=["telepathy"]))
    assert any("category 'vibes'" in e for e in errs)
    assert any("requires 'telepathy'" in e for e in errs)


def test_an_unknown_field_name_is_rejected():
    errs = errors_for(record(catgories=["doublets"]))
    assert any("unknown field 'catgories'" in e for e in errs)


@pytest.mark.parametrize("bad", ["ToyTool", "toy_tool", "-toy", "toy-", "toy tool", "töy"])
def test_ids_must_be_lowercase_slugs(bad):
    assert any("id '" in e for e in errors_for(record(id=bad)))


@pytest.mark.parametrize("good", ["toy", "toy-tool-2", "10x-cellranger"])
def test_valid_slugs_pass(good):
    assert errors_for(record(id=good)) == []


def test_duplicate_ids_across_files_name_both_files(tmp_path):
    write(tmp_path, "T1.yaml", [record()])
    write(tmp_path, "T2.yaml", [record(name="ToyTool again")])
    _, errors, _ = build.build_catalog(tmp_path, tmp_path / "none.yaml", tmp_path)
    dup = [e for e in errors if "duplicate id 'toy-tool'" in e]
    assert len(dup) == 1 and "T1.yaml" in dup[0] and "T2.yaml" in dup[0]


def test_duplicate_ids_within_one_file(tmp_path):
    write(tmp_path, "T1.yaml", [record(), record()])
    _, errors, _ = build.build_catalog(tmp_path, tmp_path / "none.yaml", tmp_path)
    assert any("duplicate id 'toy-tool'" in e and "record 1" in e and "record 2" in e
               for e in errors)


def test_nothing_is_written_when_validation_fails(tmp_path):
    write(tmp_path, "T1.yaml", [record(tier="sota")])
    out = tmp_path / "out"
    rc = build.main(["--records", str(tmp_path / "T1.yaml"), "--benchmarks",
                     str(tmp_path / "none.yaml"), "--out-dir", str(out),
                     "--cache-dir", str(tmp_path)])
    assert rc == 1 and not (out / "catalog.json").exists()


def test_benchmark_references_must_resolve():
    errs = errors_for(record(benchmarks=["nope-2020"]), bench={"xi-li-2021"})
    assert any("benchmark 'nope-2020'" in e for e in errs)
    assert errors_for(record(benchmarks=["xi-li-2021"]), bench={"xi-li-2021"}) == []


def test_benchmark_refs_resolve_against_the_benchmarks_file(tmp_path):
    write(tmp_path, "T1.yaml", [record(benchmarks=["xi-li-2021-doublet-benchmark"])])
    catalog, errors, _ = build.build_catalog(tmp_path / "T1.yaml", BENCH_SEED, tmp_path)
    assert errors == []
    ref = catalog["records"][0]["benchmark_refs"][0]
    assert ref["url"] == "https://doi.org/10.1016/j.cels.2020.11.008"
    bench = {b["id"]: b for b in catalog["benchmarks"]}
    assert bench["xi-li-2021-doublet-benchmark"]["evaluates"] == ["toy-tool"]
    # the same record against an EMPTY benchmarks file fails
    _, errors, _ = build.build_catalog(tmp_path / "T1.yaml", tmp_path / "none.yaml", tmp_path)
    assert errors


def test_benchmarks_file_is_validated(tmp_path):
    path = tmp_path / "b.yaml"
    path.write_text(yaml.safe_dump({"benchmarks": [
        {"id": "a-2020", "name": "A"}, {"id": "a-2020", "name": "A again"},
        {"id": "B", "name": "bad id", "colour": "red"}]}))
    _, errors = build.load_benchmarks(path)
    assert any("duplicate benchmark id 'a-2020'" in e for e in errors)
    assert any("unknown field 'colour'" in e for e in errors)
    assert any("lowercase slug" in e for e in errors)


def test_the_shipped_benchmarks_and_expected_files_are_valid():
    benches, errors = build.load_benchmarks(config.BENCHMARKS)
    assert errors == []
    assert isinstance(yaml.safe_load(config.EXPECTED.read_text())["expected"], list)


def test_verified_needs_an_identifier_and_a_title():
    errs = errors_for(record(verified=True))
    assert any("no doi or pmid" in e for e in errs)
    assert any("cite_title is empty" in e for e in errs)
    ok = record(verified=True, doi="10.1186/s13059-019-1662-y", cite_title="EmptyDrops: ...")
    assert errors_for(ok) == []


@pytest.mark.parametrize("doi", ["https://doi.org/10.1186/abc", "doi:10.1186/abc", "1186/abc"])
def test_doi_must_be_bare(doi):
    assert any("not a bare DOI" in e for e in errors_for(record(doi=doi)))


def test_pmid_year_and_papers_formats():
    errs = errors_for(record(pmid="PMC123", year=19, papers=["10.1/x", "pmid:12"]))
    assert any("pmid 'PMC123'" in e for e in errs)
    assert any("year '19'" in e for e in errs)
    assert any("paper '10.1/x'" in e for e in errs)
    assert not any("paper 'pmid:12'" in e for e in errs)


def test_qc_links_categories_must_exist():
    good = record(layer="adjacent", categories=["normalisation"],
                  qc_links=[{"category": "ambient-rna", "effect": "inflates size factors"}])
    assert errors_for(good) == []
    bad = record(qc_links=[{"category": "nonsense", "effect": "x"}, {"category": "doublets"}])
    errs = errors_for(bad)
    assert any("qc_links category 'nonsense'" in e for e in errs)
    assert any("needs an effect" in e for e in errs)


def test_repo_and_url_formats():
    assert errors_for(record(repo="MarioniLab/DropletUtils", url="https://x.org")) == []
    assert errors_for(record(repo="https://gitlab.com/owner/name")) == []
    errs = errors_for(record(repo="just-a-name", url="www.x.org"))
    assert any("repo 'just-a-name'" in e for e in errs)
    assert any("url 'www.x.org'" in e for e in errs)


# ---------------------------------------------------------------------------
# warnings: style, not correctness
# ---------------------------------------------------------------------------
def test_style_problems_warn_but_do_not_fail():
    rec = record(summary="Flags doublets.", caveats="fast \u2014 but rough",
                 layer="adjacent", gain="+5% cells")
    assert errors_for(rec) == []
    warns = warnings_for(rec)
    assert any("full stop" in w for w in warns)
    assert any("em-dash" in w for w in warns)
    assert any("primary category 'doublets' is in layer 'core'" in w for w in warns)
    assert any("without a gain_source" in w for w in warns)


# ---------------------------------------------------------------------------
# the derived row
# ---------------------------------------------------------------------------
def test_citations_come_from_the_cache_and_unknown_is_not_zero(tmp_path):
    (tmp_path / "citation_cache.csv").write_text(
        "identifier,citations\ndoi_10.1186_s13059-019-1662-y,1234\n")
    catalog, errors, _ = build.build_catalog(RECORDS_SEED, BENCH_SEED, tmp_path)
    rows = {r["id"]: r for r in catalog["records"]}
    assert rows["emptydrops"]["citations"] == 1234
    assert rows["soupx"]["citations"] is None
    assert "make enrich" in rows["soupx"]["citation_note"]
    assert catalog["records"][0]["id"] == "emptydrops"      # sorted by citations


def test_a_paper_claimed_by_three_records_shows_no_count(tmp_path):
    doi = "10.1000/suite"
    write(tmp_path, "T1.yaml", [record(id=f"m{i}", doi=doi) for i in range(3)])
    (tmp_path / "citation_cache.csv").write_text(f"identifier,citations\ndoi_10.1000_suite,999\n")
    catalog, _, _ = build.build_catalog(tmp_path / "T1.yaml", tmp_path / "none.yaml", tmp_path)
    assert all(r["citations"] is None for r in catalog["records"])
    assert "shared by 3 records" in catalog["records"][0]["citation_note"]


def test_papers_total_keeps_the_primary_as_headline(tmp_path):
    write(tmp_path, "T1.yaml", [record(doi="10.1000/a", papers=["doi:10.1000/b", "doi:10.1000/b"])])
    (tmp_path / "citation_cache.csv").write_text(
        "identifier,citations\ndoi_10.1000_a,10\ndoi_10.1000_b,90\n")
    catalog, _, _ = build.build_catalog(tmp_path / "T1.yaml", tmp_path / "none.yaml", tmp_path)
    row = catalog["records"][0]
    assert row["citations"] == 10 and row["publication"] == "doi:10.1000/a"
    assert row["citations_total"] == 100 and row["citations_papers"] == 2


def test_repository_activity_is_merged_from_the_github_cache(tmp_path):
    (tmp_path / "github.json").write_text(
        '{"MarioniLab/DropletUtils": {"status": "ok", "stars": 99, "pushed_at": "2026-01-02"}}')
    catalog, _, _ = build.build_catalog(RECORDS_SEED, BENCH_SEED, tmp_path)
    row = {r["id"]: r for r in catalog["records"]}["emptydrops"]
    assert row["repo_stars"] == 99 and row["repo_pushed"] == "2026-01-02"
    assert row["repo_url"] == "https://github.com/MarioniLab/DropletUtils"


def test_year_is_backfilled_from_pubmeta_but_never_overrides(tmp_path):
    write(tmp_path, "T1.yaml", [record(doi="10.1000/a"), record(id="b", doi="10.1000/b", year=2001)])
    (tmp_path / "pubmeta.json").write_text(
        '{"doi_10.1000_a": {"year": "2019", "venue": "Genome Biol"},'
        ' "doi_10.1000_b": {"year": "2020"}}')
    catalog, _, _ = build.build_catalog(tmp_path / "T1.yaml", tmp_path / "none.yaml", tmp_path)
    rows = {r["id"]: r for r in catalog["records"]}
    assert rows["toy-tool"]["year"] == "2019" and rows["toy-tool"]["publication_venue"] == "Genome Biol"
    assert rows["b"]["year"] == "2001"


def test_tsv_has_one_row_per_record(tmp_path):
    catalog, _, _ = build.build_catalog(RECORDS_SEED, BENCH_SEED, tmp_path)
    _, tsv = build.write_catalog(catalog, tmp_path / "out")
    lines = tsv.read_text().splitlines()
    assert len(lines) == 7 and lines[0].split("\t") == build.COLUMNS


def test_records_dir_can_come_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("RECORDS_DIR", str(RECORDS_SEED))
    monkeypatch.setenv("BENCHMARKS_FILE", str(BENCH_SEED))
    rc = build.main(["--out-dir", str(tmp_path), "--cache-dir", str(tmp_path)])
    assert rc == 0
    assert '"count": 6' in (tmp_path / "catalog.json").read_text()


# ---------------------------------------------------------------------------
# build-strict
# ---------------------------------------------------------------------------
def test_strict_fails_unverified_records_except_hypotheses(tmp_path):
    write(tmp_path, "T1.yaml", [record(), record(id="idea", kind="hypothesis", tier="hypothesis")])
    catalog, _, _ = build.build_catalog(tmp_path / "T1.yaml", tmp_path / "none.yaml", tmp_path)
    fails = build.strict_failures(catalog, {})
    assert len(fails) == 1 and fails[0].startswith("toy-tool")


def test_strict_allows_a_paperless_method_with_a_url_but_not_without(tmp_path):
    write(tmp_path, "T1.yaml", [
        record(id="no-paper", kind="method", url="https://example.org"),
        record(id="nothing", kind="design"),
        record(id="study", kind="evidence", url="https://example.org"),
    ])
    catalog, _, _ = build.build_catalog(tmp_path / "T1.yaml", tmp_path / "none.yaml", tmp_path)
    fails = sorted(f.split()[0] for f in build.strict_failures(catalog, {}))
    assert fails == ["nothing", "study"]


def test_strict_passes_the_verified_fixtures(tmp_path):
    catalog, _, _ = build.build_catalog(RECORDS_SEED, BENCH_SEED, tmp_path)
    assert build.strict_failures(catalog, {}) == []


def test_strict_fails_a_current_mismatch_but_not_a_stale_one(tmp_path):
    rec = yaml.safe_load(RECORDS_SEED.read_text())["records"][0]
    entry = {"status": "mismatch", "doi": rec["doi"], "pmid": str(rec["pmid"]),
             "cite_title": rec["cite_title"], "reasons": ["doi title differs"]}
    (tmp_path / "verify.json").write_text(
        __import__("json").dumps({"entries": {"record:emptydrops": entry}}))
    catalog, _, _ = build.build_catalog(RECORDS_SEED, BENCH_SEED, tmp_path)
    fails = build.strict_failures(catalog, build.load_verify(tmp_path))
    assert len(fails) == 1 and "emptydrops" in fails[0] and "doi title differs" in fails[0]

    # the record has been edited since the check: the mismatch no longer applies
    entry["cite_title"] = "an older title"
    (tmp_path / "verify.json").write_text(
        __import__("json").dumps({"entries": {"record:emptydrops": entry}}))
    catalog, _, _ = build.build_catalog(RECORDS_SEED, BENCH_SEED, tmp_path)
    assert {r["id"]: r for r in catalog["records"]}["emptydrops"]["citation_check"] == "stale"
    assert build.strict_failures(catalog, build.load_verify(tmp_path)) == []
