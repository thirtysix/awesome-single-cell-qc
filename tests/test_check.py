"""`make check`: [[id]] links in the review chapters, the denylist, recall."""
import json
from pathlib import Path

import build
import check

FIXTURES = Path(__file__).parent / "fixtures"


def test_review_links_are_parsed_outside_code_fences():
    text = "See [[demuxmix]] and [[cellbender|CellBender]].\n```\n[[in-a-fence]]\n```\n[[soupx#caveats]]\n"
    assert check.review_links(text) == [(1, "demuxmix"), (1, "cellbender"), (5, "soupx")]


def test_unresolved_links_are_reported_with_file_and_line(tmp_path):
    (tmp_path / "01-x.md").write_text("ok [[demuxmix]]\n\nbad [[no-such-record]]\n[[xi-li-2021]]\n")
    problems = check.check_review_links(tmp_path, {"demuxmix"}, {"xi-li-2021"})
    assert problems[0] == "01-x.md:3: link to no-such-record is not a record id"
    assert "benchmark id" in problems[1]
    assert len(problems) == 2


def test_markdown_record_links_are_parsed():
    text = "[demuxmix](../records.md#demuxmix), [x](records.md#nope) and [y](other.md#z)\n"
    assert check.review_links(text) == [(1, "demuxmix"), (1, "nope")]


def test_gate_opt_out_files_may_only_carry_record_ids(tmp_path):
    allow = tmp_path / ".publish-gate-allow"
    allow.write_text("# comment\nhouse-memory-link  curation/*.yaml\nother-rule  *.md\n")
    globs = check.gate_allow_globs(allow)
    assert globs == ["curation/*.yaml"]
    (tmp_path / "curation").mkdir()
    (tmp_path / "tests").mkdir()
    rec = tmp_path / "curation" / "a.yaml"
    rec.write_text("see [[demuxmix]]\nand [[some-memory-note]]\n")
    fixture = tmp_path / "tests" / "b.yaml"
    fixture.write_text("[[not-a-record]]\n")
    other = tmp_path / "notes.md"
    other.write_text("[[elsewhere]]\n")
    problems = check.check_wiki_links([rec, fixture, other], globs + ["tests/*"],
                                      {"demuxmix"}, root=tmp_path)
    assert len(problems) == 1 and problems[0].startswith("curation/a.yaml:2: [[some-memory-note]]")


def test_the_fixture_chapter_resolves_against_the_fixture_records(tmp_path):
    catalog, _, _ = build.build_catalog(FIXTURES / "records_seed.yaml",
                                        FIXTURES / "benchmarks_seed.yaml", tmp_path)
    ids = {r["id"] for r in catalog["records"]}
    assert check.check_review_links(FIXTURES / "review", ids) == []


def test_denylist_hits_name_the_entry_number_not_the_term(tmp_path):
    deny = tmp_path / ".denylist.local"
    deny.write_text("# comment\n\nSecretProject\nlocal/path/x\n")
    terms = check.load_denylist(deny)
    assert terms == [(3, "secretproject"), (4, "local/path/x")]
    a = tmp_path / "a.md"
    a.write_text("fine\nmentions secretPROJECT here\n")
    b = tmp_path / "b.bin"
    b.write_bytes(b"\0secretproject")
    hits = check.check_denylist([a, b, deny], terms, root=tmp_path)
    assert hits == ["a.md:2: matches denylist entry #3"]
    assert "secret" not in hits[0].lower()


def test_no_denylist_means_no_hits(tmp_path):
    assert check.load_denylist(tmp_path / "missing") == []
    assert check.check_denylist([tmp_path / "x"], []) == []


def test_fallback_file_walk_honours_gitignore(tmp_path, monkeypatch):
    (tmp_path / ".gitignore").write_text("dist/\n*.pyc\n")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "hub.html").write_text("x")
    (tmp_path / "keep.md").write_text("x")
    (tmp_path / "skip.pyc").write_text("x")
    monkeypatch.setattr(check.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    names = {p.name for p in check.candidate_files(tmp_path)}
    assert "keep.md" in names and "hub.html" not in names and "skip.pyc" not in names


def test_expected_recall(tmp_path):
    exp = tmp_path / "expected.yaml"
    exp.write_text("expected:\n  - emptydrops\n  - {id: cellranger, why: default}\n")
    catalog = {"records": [{"id": "emptydrops"}]}
    assert check.expected_recall(catalog, exp) == (2, ["cellranger"])


def test_check_main_passes_on_the_fixture_catalog(tmp_path, monkeypatch):
    catalog, _, _ = build.build_catalog(FIXTURES / "records_seed.yaml",
                                        FIXTURES / "benchmarks_seed.yaml", tmp_path)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    monkeypatch.setattr(check, "DENYLIST", tmp_path / "none")
    monkeypatch.setattr(check, "load_denylist", lambda path=None: [])
    assert check.main(["--catalog", str(path), "--review-dir", str(FIXTURES / "review")]) == 0


def test_check_main_fails_on_a_dangling_link(tmp_path, monkeypatch):
    catalog, _, _ = build.build_catalog(FIXTURES / "records_seed.yaml",
                                        FIXTURES / "benchmarks_seed.yaml", tmp_path)
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(catalog))
    review = tmp_path / "review"
    review.mkdir()
    (review / "01.md").write_text("[[gone]]\n")
    monkeypatch.setattr(check, "load_denylist", lambda path=None: [])
    assert check.main(["--catalog", str(path), "--review-dir", str(review)]) == 1
