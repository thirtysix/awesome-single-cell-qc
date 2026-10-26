"""README, site, standalone page and review-chapter regions, from the fixture records."""
import json
import re
import shutil
from pathlib import Path

import pytest

import build
import check
import config
import render

FIXTURES = Path(__file__).parent / "fixtures"
RECORDS_SEED = FIXTURES / "records_seed.yaml"
BENCH_SEED = FIXTURES / "benchmarks_seed.yaml"
CHAPTER = FIXTURES / "review" / "01-demux-recovery.md"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def catalog(tmp_path):
    cat, errors, _ = build.build_catalog(RECORDS_SEED, BENCH_SEED, tmp_path / "cache")
    assert not errors
    return cat


@pytest.fixture
def empty_catalog(tmp_path):
    (tmp_path / "records").mkdir()
    cat, errors, _ = build.build_catalog(tmp_path / "records", tmp_path / "none.yaml", tmp_path)
    assert not errors
    return cat


def records_from_js(js: str) -> list:
    m = re.search(r"const RECORDS = (\[.*?\]);\n", js, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------
def test_readme_has_title_intro_contents_and_build_section(catalog):
    md = render.render_readme(catalog)
    assert md.startswith("# Awesome Single-Cell QC\n")
    assert "salvaging cells and signal in multiplexed" in md
    assert "## Contents" in md and "## How this list is built" in md
    assert "YAML" in md or ".yaml" in md
    for step in ("build.py", "verify_citations.py", "render.py"):
        assert step in md


def test_readme_contents_lists_every_category_with_its_count(catalog):
    md = render.render_readme(catalog)
    assert "[Cell calling](#cell-calling), 2 records" in md
    assert "[Hashing demultiplexing](#hashing-demultiplexing), 1 record" in md
    assert "Genotype demultiplexing, 0 records" in md
    for key in config.CATEGORY_KEYS:
        assert config.CATEGORY_LABEL[key] in md


def test_readme_entries_carry_tier_badge_and_gain(catalog):
    md = render.render_readme(catalog)
    line = next(l for l in md.splitlines() if l.startswith("- **[CellBender]"))
    assert "`benchmarked-sota`" in line
    assert "Gain: lowest residual background" in md and "(independent)" in md
    assert "bio.tools" not in md


def test_readme_section_anchors_match_github_slugs(catalog):
    md = render.render_readme(catalog)
    headings = {render.slug(h) for h in re.findall(r"^#{2,3} (.+)$", md, re.M)}
    for anchor in re.findall(r"\]\(#([^)]+)\)", md):
        assert anchor in headings, anchor


def test_readme_orders_entries_by_tier_then_citations(catalog):
    md = render.render_readme(catalog)
    section = md.split("### Cell calling")[1].split("###")[0]
    assert section.index("EmptyDrops") < section.index("CellBender")   # standard first


def test_readme_with_no_records_says_so(empty_catalog):
    md = render.render_readme(empty_catalog)
    assert "No records yet" in md
    assert "## How this list is built" in md


def test_no_em_dashes_in_generated_text(catalog):
    md = render.render_readme(catalog)
    assert "\u2014" not in md
    assert "\u2014" not in render.render_site(catalog, CHAPTER.parent)
    assert "\u2014" not in render.render_hub(catalog, CHAPTER.parent)


def test_preprint_links_are_labelled(catalog):
    row = dict(catalog["records"][0], publication="doi:10.1101/2023.03.17.533005",
               publication_url="https://doi.org/10.1101/2023.03.17.533005",
               publication_is_preprint=True)
    assert "[preprint](" in "\n".join(render.tool_line(row))


def test_site_url_ignores_code_hosts_and_the_repo():
    assert render.site_url({"url": "https://github.com/a/b", "repo_url": ""}) == ""
    assert render.site_url({"url": "https://x.org/", "repo_url": "https://x.org"}) == ""
    assert render.site_url({"url": "https://bioconductor.org/packages/x",
                            "repo_url": "https://github.com/a/x"}) == "https://bioconductor.org/packages/x"


# ---------------------------------------------------------------------------
# site
# ---------------------------------------------------------------------------
def test_site_is_the_hub_as_a_whole_page(catalog, tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "catalog.js").write_text("stale")
    index = render.write_site(catalog, docs, CHAPTER.parent)
    html = index.read_text()
    assert not (docs / "catalog.js").exists()
    assert html.startswith("<!doctype html>") and '<meta charset="utf-8">' in html
    assert 'name="viewport"' in html and html.rstrip().endswith("</html>")
    assert "claude:" not in html
    assert 'data-view="catalog"' in html and 'data-nav="ch01"' in html
    rows = records_from_js(html)
    assert len(rows) == 6 and {r["id"] for r in rows} >= {"emptydrops", "dreamlet"}


@pytest.mark.parametrize("control", ["layer", "kind", "tier", "side", "requires"])
def test_site_has_a_filter_for(catalog, control):
    assert f'<select id="{control}"' in render.render_site(catalog, CHAPTER.parent)


@pytest.mark.parametrize("column", ["Name", "Categories", "Kind", "Tier", "Side",
                                    "Recovers / gain", "Requires", "Year", "Citations", "Links"])
def test_site_has_column(catalog, column):
    assert f">{column}</th>" in render.render_site(catalog, CHAPTER.parent)


def test_site_vocabulary_comes_from_the_schema(catalog):
    html = render.render_site(catalog, CHAPTER.parent)
    vocab = json.loads(re.search(r"const VOCAB = (\{.*?\});\n", html).group(1))
    assert [t[0] for t in vocab["tiers"]] == list(config.TIERS)
    assert [c[0] for c in vocab["categories"]] == config.CATEGORY_KEYS
    assert [r[0] for r in vocab["requires"]] == list(config.REQUIRES)


def test_site_keeps_the_light_dark_theme(catalog):
    html = render.render_site(catalog, CHAPTER.parent)
    assert "prefers-color-scheme: dark" in html
    # dark by preference unless toggled to light; dark when toggled to dark
    assert ':root:not([data-theme="light"])' in html and ':root[data-theme="dark"]' in html
    assert 'id="theme"' in html


def test_zero_counts_survive_the_slim_payload(catalog):
    catalog["records"][0]["citations"] = 0
    rows = render.slim_records(catalog)
    assert rows[0]["citations"] == 0


# ---------------------------------------------------------------------------
# standalone page
# ---------------------------------------------------------------------------
def test_standalone_page_inlines_the_catalog(catalog, tmp_path):
    path = render.write_standalone(catalog, tmp_path / "dist" / "hub.html", CHAPTER.parent)
    html = path.read_text()
    assert "catalog.js" not in html
    assert "const STANDALONE = true" in html
    assert len(records_from_js(html)) == 6
    # nothing fetched from anywhere: no external scripts, stylesheets or fonts
    assert not re.search(r"<script[^>]+src=", html)
    assert not re.search(r"<link[^>]+href=", html)
    assert "@import" not in html


def test_standalone_escapes_a_closing_script_tag_in_data(catalog):
    catalog["records"][0]["summary"] = "evil </script><script>alert(1)</script>"
    html = render.render_hub(catalog, CHAPTER.parent)
    assert "evil </script>" not in html
    assert "evil <\\/script>" in html


def test_standalone_cli_writes_only_the_page(catalog, tmp_path):
    cat_path = tmp_path / "catalog.json"
    cat_path.write_text(json.dumps(catalog))
    out = tmp_path / "hub.html"
    before = CHAPTER.read_text()
    assert render.main(["--catalog", str(cat_path), "--standalone", "--out", str(out),
                        "--review-dir", str(CHAPTER.parent)]) == 0
    assert 'data-view="ch01"' in out.read_text()
    assert CHAPTER.read_text() == before          # the page reads chapters, never writes them


# ---------------------------------------------------------------------------
# hub page: the artifact page contract
# ---------------------------------------------------------------------------
@pytest.fixture
def hub(catalog):
    return render.render_hub(catalog, CHAPTER.parent)


def markup(page: str) -> str:
    """The page without its scripts, styles and code blocks."""
    return re.sub(r"<script>.*?</script>|<style>.*?</style>|<pre>.*?</pre>", "", page, flags=re.S)


def style(page: str) -> str:
    return page[page.index("<style>"):page.index("</style>")]


def test_hub_is_page_content_without_a_document_skeleton(hub):
    assert not re.search(r"<!doctype|<html[\s>]|</html>|<head[\s>]|</head>|<body[\s>]|</body>",
                         hub, re.I)
    assert hub.startswith("<title>Awesome Single-Cell QC</title>")


def test_hub_title_viewport_meta_and_style_are_in_the_first_8_kb(hub):
    head = hub[:8192]
    assert "<title>Awesome Single-Cell QC</title>" in head
    assert '<meta name="claude:viewport-fit-sides" content="cover">' in head
    assert "<style>" in head


def test_hub_colours_are_tokens_with_light_and_both_dark_blocks(hub):
    css = style(hub)
    light = re.search(r"^:root \{(.*?)^\}", css, re.S | re.M)
    media = re.search(r'@media \(prefers-color-scheme: dark\) \{\s*'
                      r':root:not\(\[data-theme="light"\]\) \{(.*?)\}', css, re.S)
    toggled = re.search(r':root\[data-theme="dark"\] \{(.*?)\}', css, re.S)
    names = lambda block: set(re.findall(r"--([\w-]+):", block))
    assert names(media.group(1)) == names(toggled.group(1))
    assert names(media.group(1)) <= names(light.group(1))
    assert "color-scheme: dark" in media.group(1) and "color-scheme: dark" in toggled.group(1)
    assert re.search(r"\nbody \{[^}]*background: var\(--bg\);[^}]*color: var\(--fg\);", css)
    rules = css
    for block in (light, media, toggled):
        rules = rules.replace(block.group(0), "")
    # no component rule names a colour of its own
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\(|(?<![\w-])(?:white|black)(?![\w-])",
                          rules)


def test_hub_side_gutter_and_safe_area_top(hub):
    css = style(hub)
    body = re.search(r"\nbody \{(.*?)\}", css, re.S).group(1)
    assert "padding-left: max(16px, env(safe-area-inset-left, 0px));" in body
    assert "padding-right: max(16px, env(safe-area-inset-right, 0px));" in body
    assert "padding-block:" in body and not re.search(r"(?<![\w-])padding:", body)
    assert re.search(r"body::before \{[^}]*height: env\(safe-area-inset-top, 0px\)", css)
    assert "top: env(safe-area-inset-top, 0px)" in css          # the sticky strip
    assert not re.search(r"(?m)^:root \{[^}]*\bpadding", css)   # the host pads :root


def test_hub_has_no_downloads_dialogs_or_fetches(hub):
    assert not re.search(r"<a\b[^>]*\bdownload\b", hub)
    for banned in ("fetch(", ".download", "createObjectURL", 'id="dl"', "alert(", "confirm(",
                   "prompt(", "window.print"):
        assert banned not in hub, banned
    assert f'<a href="{render.REPO_URL}">' in hub and "private" not in hub


def test_site_keeps_its_download_button(catalog):
    html = render.render_site(catalog, CHAPTER.parent)
    assert 'id="dl"' in html and "createObjectURL" in html


def test_hub_links_are_plain_tokens_https_and_quoted(hub):
    page = markup(hub)
    for target in re.findall(r'href="#([^"]*)"', page):
        assert render.HASH_TOKEN.match(target), target
    for target in re.findall(r'href="(?!#)([^"]*)"', page):
        assert target.startswith("https://"), target
    for tag in re.findall(r"<[a-zA-Z][^<>]*>", page):
        assert not re.search(r"\s[a-zA-Z:-]+=[^\"\s>]", tag), tag
    ids = re.findall(r'\sid="([^"]+)"', page)
    assert len(ids) == len(set(ids))


def test_hub_shows_one_view_at_a_time(hub):
    assert re.findall(r'data-view="([^"]+)"', hub) == ["ch01", "catalog"]
    # the catalog is the landing view; every chapter starts hidden
    assert re.search(r'<section class="view" data-view="ch01"[^>]*>', hub).group(0).endswith(" hidden>")
    assert "hidden" not in re.search(r'<section class="view catalog" data-view="catalog"[^>]*>', hub).group(0)
    assert hub.index('data-nav="catalog"') < hub.index('data-nav="ch01"')
    assert 'href="#ch01" data-nav="ch01"' in hub and 'href="#catalog" data-nav="catalog"' in hub


def test_hub_header_counts_records_by_tier_with_a_legend(hub, catalog):
    assert "6 records" in hub and "built " + catalog["meta"]["generated"] in hub
    assert "How to read tiers" in hub
    for i, (tier, desc) in enumerate(config.TIERS.items()):
        assert f'<span class="tier t{min(i, 4)}">{tier}</span>' in hub
        assert desc.replace("&", "&amp;") in hub


# ---------------------------------------------------------------------------
# hub page: chapters
# ---------------------------------------------------------------------------
CHAPTER_MD = """# 03. A chapter: with a subtitle

Intro with **bold**, *italic*, `code`, BFF_raw and BFF_cluster, a [[demuxmix]] link,
a [[emptydrops|named link]] and a [[dreamlet#downstream]] link. See PMID
34159316 and [PMID 31237234](https://pubmed.ncbi.nlm.nih.gov/31237234/), and the
[overview](00-overview.md).

## A section

- one item
  continued on the next line
- two, again [[emptydrops]]

1. first
2. second, in a sentence that wraps after
2020. Still the second item.

| Stage | Count |
|---|---:|
| Calling | [[emptydrops]] |

<!-- a comment -->
<a id="anchor-x"></a>Text after an anchor.

<!-- records:start -->
| stale | table |
<!-- records:end -->
"""


@pytest.fixture
def chapter(catalog, tmp_path):
    (tmp_path / "00-overview.md").write_text("# Overview\n\nSee [chapter 3](03-chapter.md).\n")
    (tmp_path / "03-chapter.md").write_text(CHAPTER_MD)
    views = render.hub_views(catalog, tmp_path)
    assert [v.token for v in views] == ["overview", "ch03"]
    return views


def test_chapter_title_drops_its_number_and_the_label_its_subtitle(chapter):
    assert chapter[1].title == "A chapter: with a subtitle"
    assert chapter[1].short == "A chapter"
    assert chapter[0].short == "Overview"


def test_chapter_inline_markdown(chapter):
    html = chapter[1].html
    assert "<strong>bold</strong>" in html and "<em>italic</em>" in html
    assert "<code>code</code>" in html
    assert "BFF_raw and BFF_cluster" in html                    # no italics mid-word
    assert "a comment" not in html and "<!--" not in html


def test_chapter_record_refs_link_to_the_catalog(chapter):
    view = chapter[1]
    assert re.search(r'<a id="ch03-m-demuxmix" href="#demuxmix" class="rec t3"[^>]*>demuxmix</a>',
                     view.html)
    assert re.search(r'href="#emptydrops" class="rec t0"[^>]*>named link</a>', view.html)
    assert 'href="#dreamlet"' in view.html
    assert view.page.refs == 5 and "[[" not in view.html
    # only the first mention carries an id, so the review can point back at it
    assert view.html.count('id="ch03-m-emptydrops"') == 1


def test_markdown_record_links_render_like_wiki_links(catalog):
    records = {t["id"]: t for t in catalog["records"]}
    wiki = "A [[demuxmix]] link, a [[emptydrops|named link]].\n"
    md = render.md_refs(wiki, records, "../records.md")
    assert "[[" not in md and "](../records.md#demuxmix)" in md
    assert "[named link](../records.md#emptydrops)" in md
    assert render.md_refs("[[no-such-record]]", records, "") == "[[no-such-record]]"
    html = [render.ReviewPage("ch01", records, {}).inline(x) for x in (wiki, md)]
    assert html[0] == html[1]


def test_records_md_anchors_every_record_once(catalog):
    md = render.render_records_md(catalog)
    for t in catalog["records"]:
        assert md.count(f'<a id="{t["id"]}"></a>') == 1, t["id"]
    assert "[[" not in md


def test_chapter_pmids_link_to_pubmed_once(chapter):
    html = chapter[1].html
    assert '<a href="https://pubmed.ncbi.nlm.nih.gov/34159316/">PMID 34159316</a>' in html
    assert html.count("pubmed.ncbi.nlm.nih.gov/31237234/") == 1


def test_chapter_links_to_other_chapters_open_their_views(chapter):
    assert '<a href="#overview">overview</a>' in chapter[1].html
    assert '<a href="#ch03">chapter 3</a>' in chapter[0].html


def test_chapter_blocks(chapter):
    html = chapter[1].html
    assert '<h2 id="ch03-a-section">A section</h2>' in html
    assert "<li>one item continued on the next line</li>" in html
    ol = re.search(r"<ol>(.*?)</ol>", html, re.S).group(1)
    assert ol.count("<li>") == 2 and "2020. Still the second item." in ol
    assert '<table class="md">' in html and '<th class="r">Count</th>' in html
    assert '<span class="anchor" id="ch03-anchor-x"></span>' in html
    assert chapter[1].page.toc[0] == (2, "A section", "ch03-a-section")


def test_chapter_records_region_becomes_a_table_of_its_records(chapter, catalog):
    view = chapter[1]
    assert "stale" not in view.html
    assert '<h2 id="ch03-records">Records in this chapter</h2>' in view.html
    assert "No records point at this chapter yet." in view.html    # none name 03-chapter
    assert view.page.toc[-1] == (2, "Records in this chapter", "ch03-records")


def test_fixture_chapter_lists_its_records_from_the_catalog(catalog):
    (view,) = render.hub_views(catalog, CHAPTER.parent)
    region = view.html[view.html.index('id="ch01-records"'):]
    assert "demuxmix" in region and "dreamlet" in region and "EmptyDrops" not in region
    assert '<tr id="ch01-m-dreamlet">' in region      # not cited in the text: its row is the target
    assert "[[not-a-record]] inside a code fence" in view.html
    assert view.page.refs == 1


def test_review_index_points_each_record_at_its_chapter(catalog):
    views = render.hub_views(catalog, CHAPTER.parent)
    link, cited = render.review_index(views, catalog["records"])
    assert link["demuxmix"] == ["ch01", "ch01-m-demuxmix"]
    assert link["dreamlet"] == ["ch01", "ch01-m-dreamlet"]
    assert "emptydrops" not in link                    # its chapter is not on the page
    assert cited == {"demuxmix": [["ch01", "ch01-m-demuxmix"]]}


def test_hub_with_no_chapters_opens_on_the_catalog(catalog, tmp_path):
    html = render.render_hub(catalog, tmp_path / "missing")
    assert re.findall(r'data-view="([^"]+)"', html) == ["catalog"]
    assert 'data-view="catalog" aria-labelledby="catalog-title">' in html


# ---------------------------------------------------------------------------
# hub page: the real chapters (skipped until `make build` has run)
# ---------------------------------------------------------------------------
REAL_CATALOG = ROOT / "data" / "catalog.json"
REAL_REVIEW = ROOT / "docs" / "review"


@pytest.fixture
def real_catalog():
    if not REAL_CATALOG.exists() or not list(REAL_REVIEW.glob("0*.md")):
        pytest.skip("needs data/catalog.json (make build) and docs/review")
    return json.loads(REAL_CATALOG.read_text())


def test_hub_has_one_view_per_review_chapter(real_catalog):
    chapters = sorted(REAL_REVIEW.glob("[0-9][0-9]-*.md"))
    views = render.hub_views(real_catalog, REAL_REVIEW)
    assert [v.stem for v in views] == [p.stem for p in chapters]
    assert views[0].token == "overview"
    html = render.render_hub(real_catalog, REAL_REVIEW)
    assert re.findall(r'data-view="([^"]+)"', html) == [v.token for v in views] + ["catalog"]


def test_every_record_ref_in_the_chapters_became_a_link(real_catalog):
    for view in render.hub_views(real_catalog, REAL_REVIEW):
        # The records:start/end region is rebuilt from the catalog, not converted.
        text = render.REGION.sub("", (REAL_REVIEW / f"{view.stem}.md").read_text())
        refs = check.review_links(text)
        assert view.page.refs == len(refs), view.stem
        assert "[[" not in re.sub(r"<pre>.*?</pre>", "", view.html, flags=re.S), view.stem
        for _, rid in refs:
            assert f'href="#{rid}" class="rec' in view.html, (view.stem, rid)


# ---------------------------------------------------------------------------
# review chapters: only the marked region changes
# ---------------------------------------------------------------------------
PROSE_BEFORE = "# Chapter\n\nHand-written intro with **bold** and a [[demuxmix]] link.\n\n"
PROSE_AFTER = "\n\n## demuxmix\n\nMore prose, untouched.\n"


def test_fill_markers_replaces_only_the_region():
    text = PROSE_BEFORE + "<!-- records:start -->\nOLD TABLE\n<!-- records:end -->" + PROSE_AFTER
    new = render.fill_markers(text, "NEW TABLE")
    assert new.startswith(PROSE_BEFORE + "<!-- records:start -->")
    assert new.endswith("<!-- records:end -->" + PROSE_AFTER)
    assert "OLD TABLE" not in new and "NEW TABLE" in new
    assert render.fill_markers(new, "NEW TABLE") == new          # idempotent


def test_fill_markers_leaves_backslashes_alone():
    text = "<!-- records:start --><!-- records:end -->"
    assert "a\\1b" in render.fill_markers(text, "a\\1b")


@pytest.mark.parametrize("broken", [
    "<!-- records:start -->\nno end",
    "no start\n<!-- records:end -->",
    "<!-- records:end -->\n<!-- records:start -->",
    "<!-- records:start --><!-- records:start --><!-- records:end -->",
])
def test_unbalanced_markers_are_not_rewritten(broken):
    assert render.fill_markers(broken, "T") is None


def test_render_review_fills_the_fixture_chapter_identically(catalog, tmp_path):
    """The committed fixture already holds the rendered table: rendering converges."""
    review = tmp_path / "review"
    review.mkdir()
    shutil.copy(CHAPTER, review / CHAPTER.name)
    results = render.render_review(catalog, review)
    assert results == [(review / CHAPTER.name, "unchanged")]
    assert (review / CHAPTER.name).read_text() == CHAPTER.read_text()


def test_render_review_touches_only_marked_chapters(catalog, tmp_path):
    review = tmp_path / "review"
    review.mkdir()
    plain = review / "02-cell-calling.md"
    plain.write_text("# No markers here\n\n[[emptydrops]]\n")
    marked = review / "01-demux-recovery.md"
    marked.write_text(PROSE_BEFORE + "<!-- records:start -->\n<!-- records:end -->" + PROSE_AFTER)
    empty = review / "09-unused.md"
    empty.write_text("<!-- records:start -->x<!-- records:end -->\n")
    render.render_review(catalog, review)
    assert plain.read_text() == "# No markers here\n\n[[emptydrops]]\n"
    out = marked.read_text()
    assert out.startswith(PROSE_BEFORE) and out.endswith(PROSE_AFTER)
    assert "[demuxmix](#demuxmix)" in out and "[dreamlet](#downstream)" in out
    assert "EmptyDrops" not in out          # its review points at another chapter
    assert "No records point at this chapter yet" in empty.read_text()


def test_render_review_with_no_review_dir_is_a_no_op(catalog, tmp_path):
    assert render.render_review(catalog, tmp_path / "missing") == []


def test_chapter_tables_do_not_reorder_when_citation_counts_change(catalog):
    rows = [r for r in catalog["records"] if r["review"].startswith("01-demux-recovery")]
    before = render.chapter_table(rows)
    for r in rows:
        r["citations"] = 10_000 if r["id"] == "dreamlet" else 1
    assert render.chapter_table(rows) == before


def _concept(rid, cat, links):
    return {"id": rid, "name": rid.title(), "kind": "concept", "layer": "adjacent",
            "categories": [cat], "side": "neutral", "tier": "standard",
            "summary": f"{rid} definition", "qc_links": links}


def test_concept_map_draws_one_edge_per_qc_link_and_lists_them(catalog, tmp_path):
    cat = dict(catalog)
    cat["records"] = list(catalog["records"]) + [
        _concept("concept-normalisation", "normalisation",
                 [{"category": "ambient-rna", "effect": "inflates size factors (PMID 12345678)"},
                  {"category": "doublets", "effect": "doubles library size"}]),
        _concept("concept-trajectories", "trajectories",
                 [{"category": "doublets", "effect": "false intermediate states"}]),
    ]
    (tmp_path / "20-map.md").write_text("# Map\n\nIntro.\n\n<!-- concept-map -->\n\nAfter.\n")
    [view] = render.hub_views(cat, tmp_path)
    html = view.html
    assert html.count('<path class="e"') == 3
    assert html.count('class="n q"') == 2              # ambient-rna, doublets: linked QC only
    assert 'href="#concept-normalisation"' in html
    assert "https://pubmed.ncbi.nlm.nih.gov/12345678/" in html
    assert html.index("Intro.") < html.index("cmap-svg") < html.index("After.")
    assert ("2", "Concept map", "ch20-map") == tuple(map(str, view.page.toc[0]))
    assert "concept-trajectories" in view.page.mentions


def test_concept_map_without_concepts_says_so(catalog, tmp_path):
    (tmp_path / "20-map.md").write_text("# Map\n\n<!-- concept-map -->\n")
    [view] = render.hub_views(catalog, tmp_path)
    assert "No concept records with qc_links yet" in view.html
