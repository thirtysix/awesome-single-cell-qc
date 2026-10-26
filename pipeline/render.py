#!/usr/bin/env python3
"""Stage 4 - render the catalog into README.md, the browsable site and the review tables.

    README.md                    per-category top entries, short enough to read
    docs/records.md              every record, each with an anchor: the target of
                                 record links in the README and the chapters
    docs/index.html              the site (GitHub Pages): the catalog, then the
                                 review chapters from a top menu, in one file
    docs/review/*.md             only the region between `<!-- records:start -->`
                                 and `<!-- records:end -->`; the rest is hand-written
    dist/hub.html                (--standalone) the review chapters and the catalog
                                 in one self-contained file, for publishing as a
                                 single page

    python pipeline/render.py [--review-dir DIR] [--standalone]
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from config import (CATEGORIES, CATEGORY_DESC, CATEGORY_KEYS, CATEGORY_LABEL,
                    CATEGORY_LAYER, CODE_HOSTS, DATA, DIST, DOCS, GAIN_SOURCES,
                    KINDS, LAYERS, REQUIRES, REVIEW_DIR, ROOT, SIDES, TIERS)
from mdutil import cell

CATALOG = DATA / "catalog.json"
README = ROOT / "README.md"
RECORDS_MD = DOCS / "records.md"
INDEX = DOCS / "index.html"
STANDALONE = DIST / "hub.html"

TITLE = "Awesome Single-Cell QC"
TOP_N = 8            # README entries per category; the rest are on the site

MARK_START = re.compile(r"<!--\s*records:start\s*-->")
MARK_END = re.compile(r"<!--\s*records:end\s*-->")
REGION = re.compile(r"(<!--\s*records:start\s*-->)(.*?)(<!--\s*records:end\s*-->)", re.S)
# `<!-- concept-map -->` in a chapter becomes the QC-to-concept map on the hub page.
MAP_MARK = re.compile(r"<!--\s*concept-map\s*-->")
# Chapters link a record as [label](../records.md#id), which GitHub follows to the
# record's entry in docs/records.md; the hub page reads it like [[id]].
RECORD_MD_LINK = re.compile(r"\[([^\[\]]+)\]\(\s*(?:\.\./)?records\.md#([a-z0-9-]+)\s*\)")


def fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return ""


def _norm_url(u: str) -> str:
    return (u or "").rstrip("/").lower().replace("://www.", "://")


def site_url(t: dict) -> str:
    """The record's own website, when that is something other than its repository.

    A homepage that is just the GitHub page duplicates the code link, so a
    "site" is a url that is neither the source repository nor any other code
    host: the package page, documentation or web server you would cite.
    """
    homepage = t.get("url") or ""
    if not homepage:
        return ""
    host = urlparse(homepage).netloc.lower().removeprefix("www.")
    if host in CODE_HOSTS:
        return ""
    if _norm_url(homepage) == _norm_url(t.get("repo_url")):
        return ""
    return homepage


def slug(label: str) -> str:
    """GitHub's heading-anchor rule: lowercase, drop punctuation, spaces to hyphens."""
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", label.lower()))


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def layer_title(key: str) -> tuple[str, str]:
    """(heading, subtitle) for a layer, from its schema description.

    The schema describes a layer as "what it is: how deeply it is covered"; the
    part before the colon is the heading and the rest the subtitle, so the
    headings are not a second vocabulary to keep in step.
    """
    desc = LAYERS.get(key) or key
    head, _, sub = desc.partition(":")
    head = head.strip()
    return (head[:1].upper() + head[1:]) if head else key, sub.strip()


def tier_rank(t: dict) -> int:
    order = list(TIERS)
    return order.index(t["tier"]) if t["tier"] in order else len(order)


def top_order(t: dict) -> tuple:
    """README order: tier in schema order, then citations, then name."""
    return (tier_rank(t), -int(t.get("citations") or 0), t["name"].lower())


def gain_text(t: dict) -> str:
    gain = (t.get("gain") or "").rstrip(".")
    src = t.get("gain_source") or ""
    if gain and src and src != "none":
        return f"{gain} ({src})"
    return gain


def md_refs(text: str, records: dict, base: str) -> str:
    """[[id]] in record text as a Markdown link to the record's entry in
    docs/records.md (`base` is that file's path from the page). An id that names
    no record is left as written."""
    def sub(m: re.Match) -> str:
        t = records.get(m.group(1).strip())
        if t is None:
            return m.group(0)
        label = (m.group(2) or "").strip() or ref_label(t)[0]
        return f"[{label}]({base}#{t['id']})"
    return RECORD_REF.sub(sub, text)


def tool_line(t: dict, records: dict | None = None, base: str = "docs/records.md",
              anchor: bool = False) -> list[str]:
    """One README entry, as two lines.

    GitHub renders a README in a fixed-width column, so the summary keeps the
    first line and everything else (what it recovers, the gain and who measured
    it, links, signals) goes on an indented second line in small type.
    """
    def refs(text: str) -> str:
        return md_refs(text, records, base) if records else text

    href = t.get("url") or t.get("repo_url") or t.get("publication_url")
    head = f"**[{t['name']}]({href})**" if href else f"**{t['name']}**"
    if anchor:
        head = f'<a id="{t["id"]}"></a>{head}'
    rows = [f"- {head} `{t['tier']}`: {refs(t['summary'].rstrip('.'))}"]

    parts = []
    if t.get("recovers"):
        parts.append(f"Recovers: {refs(t['recovers'].rstrip('.'))}")
    if gain_text(t):
        parts.append(f"Gain: {refs(gain_text(t))}")
    links = []
    if t.get("repo_url"):
        links.append(f"[code]({t['repo_url']})")
    if t.get("publication_url"):
        label = "preprint" if t.get("publication_is_preprint") else "paper"
        links.append(f"[{label}]({t['publication_url']})")
    signals = []
    if t.get("citations"):
        cites = f"{fmt_int(t['citations'])} cites"
        if t.get("citations_total") and t.get("citations_papers"):
            cites += f", {fmt_int(t['citations_total'])} across {t['citations_papers']} papers"
        signals.append(cites)
    if t.get("repo_stars"):
        signals.append(f"{fmt_int(t['repo_stars'])} stars")
    if t.get("repo_archived"):
        signals.append("archived")
    meta = " · ".join(parts + links)
    if signals:
        meta += (" · " if meta else "") + f"`{' | '.join(signals)}`"
    if meta:
        rows.append(f"  <sub>{meta}</sub>")
    return rows


def render_readme(catalog: dict) -> str:
    records = catalog.get("records") or []
    by_id = {t["id"]: t for t in records}
    meta = catalog["meta"]
    by_cat: dict[str, list] = {k: [] for k in CATEGORY_KEYS}
    for t in records:
        for c in t["categories"]:
            by_cat.setdefault(c, []).append(t)
    total = len(records)
    by_layer = meta.get("by_layer") or {}

    out: list[str] = []
    A = out.append
    A(f"# {TITLE}")
    A("")
    if total:
        A(f"[![Records](https://img.shields.io/badge/records-{total}-blue)]({SITE_URL}) "
          f"[![Site](https://img.shields.io/badge/browse-interactive%20catalog-teal)]({SITE_URL}) "
          "[![Data: CC BY 4.0](https://img.shields.io/badge/data-CC--BY--4.0-lightgrey)](LICENSE-DATA) "
          "[![Code: MIT](https://img.shields.io/badge/code-MIT-lightgrey)](LICENSE)")
        A("")
        A(f"### **[Open the interactive catalog and review →]({SITE_URL})**")
        A("")
        A("Search, filter and sort every record, open any one for its evidence and "
          "citation, hover a column header or chip for what it means, and read the "
          "review chapters, all on one page.")
        A("")
        A(f'<a href="{SITE_URL}"><img src="docs/screenshots/catalog.webp" '
          'alt="The catalog: category chips, summary panels and the record table" width="100%"></a>')
        A("")
        A(f'<a href="{SITE_URL}#demuxmix"><img src="docs/screenshots/record.webp" '
          'alt="A record opened for its details, with a column-header tooltip" width="49%"></a> '
          f'<a href="{SITE_URL}#ch01"><img src="docs/screenshots/chapter.webp" '
          'alt="A review chapter, opened from the Chapters menu" width="49%"></a>')
        A("")
    A("A comprehensive catalog of single-cell QC and preprocessing tools, methods and "
      "evidence, with an emphasis on **salvaging cells and signal in multiplexed "
      "experiments**, plus a map of the adjacent concepts that QC choices feed into.")
    A("")
    if total:
        layer_counts = ", ".join(f"{by_layer.get(k, 0)} {k}" for k in LAYERS)
        nb = meta.get("benchmarks", 0)
        A(f"**{plural(total, 'record')}** ({layer_counts}) and "
          f"{nb} benchmark {'study' if nb == 1 else 'studies'}, built "
          f"{meta['generated']}. Every entry carries a tier, the side it works on "
          "(keeping cells, removing them, or either), what it needs as input, and, "
          "where it recovers cells or signal, the reported gain and who measured it.")
    else:
        A(f"**No records yet** (built {meta['generated']}). The research tracks are "
          "still writing `curation/records/`; this page fills in on the next "
          "`make curate`.")
    A("")
    A(f"The site at {SITE_URL} is `docs/index.html` (`make serve`, then "
      "http://127.0.0.1:8510/, to run it locally). On GitHub, "
      "[docs/records.md](docs/records.md) lists every record.")
    A("")

    A("## Contents")
    A("")
    for layer in LAYERS:
        head, _ = layer_title(layer)
        A(f"- [{head}](#{slug(head)})")
        for key in CATEGORY_KEYS:
            if CATEGORY_LAYER[key] != layer:
                continue
            n = len(by_cat[key])
            label = CATEGORY_LABEL[key]
            A(f"  - [{label}](#{slug(label)}), {plural(n, 'record')}" if n
              else f"  - {label}, 0 records")
    A("- [Tiers](#tiers)")
    A("- [How this list is built](#how-this-list-is-built)")
    A("- [Licence](#licence)")
    A("")

    for layer in LAYERS:
        head, sub = layer_title(layer)
        A(f"## {head}")
        A("")
        if sub:
            A(f"*{sub[:1].upper() + sub[1:]}.*")
            A("")
        for key in CATEGORY_KEYS:
            if CATEGORY_LAYER[key] != layer or not by_cat[key]:
                continue
            entries = sorted(by_cat[key], key=top_order)
            A(f"### {CATEGORY_LABEL[key]}")
            A("")
            A(f"*{CATEGORY_DESC[key]}*")
            A("")
            for t in entries[:TOP_N]:
                out.extend(tool_line(t, by_id))
            A("")
            rest = len(entries) - TOP_N
            if rest > 0:
                A(f"<sub>+ {rest} more in this category in the "
                  f"[catalog](docs/index.html?category={key})</sub>")
                A("")

    A("## Tiers")
    A("")
    A("| Tier | Meaning |")
    A("| --- | --- |")
    for key, desc in TIERS.items():
        A(f"| `{key}` | {cell(desc)} |")
    A("")
    A("A gain is labelled with who measured it: "
      + "; ".join(f"`{k}` {v}" for k, v in GAIN_SOURCES.items()) + ".")
    A("")

    A("## How this list is built")
    A("")
    A("Every entry is a hand-written YAML record; everything else is generated from "
      "the records and is never edited by hand.")
    A("")
    A("```")
    A("curation/records/*.yaml   the records, one file per research track")
    A("curation/schema.yaml      the vocabulary every record is validated against")
    A("curation/benchmarks.yaml  benchmark studies the records point at")
    A("        |")
    A("        v")
    A("build.py             validate, merge cached metadata -> data/catalog.json, .tsv")
    A("verify_citations.py  fetch each DOI (Crossref) and PMID (PubMed), match the")
    A("                     title, check both name one work -> docs/citation-check.md")
    A("enrich.py            citation counts (OpenAlex), repository activity (GitHub)")
    A("render.py            README.md, docs/index.html (the site), chapter tables,")
    A("                     dist/hub.html")
    A("```")
    A("")
    A("- **Validate.** `make build` rejects a record with a missing required field, a "
      "value outside the schema's vocabulary, a malformed id or identifier, a "
      "benchmark reference that does not resolve, or an id already used in another "
      "file. Nothing is written until every record passes.")
    A("- **Verify.** A record says `verified: true` only when its DOI or PMID was "
      "fetched and the returned title matched `cite_title`. `make verify` re-checks "
      "that against Crossref and PubMed (cached; only a 404 counts as broken), and "
      "`make build-strict` refuses to ship any unverified record other than a "
      "`hypothesis` or a tool, method or design that cites no primary paper "
      "and links a homepage, repository or supporting papers instead, and any "
      "record the last check contradicted.")
    A("- **Render.** `make curate` rebuilds the catalog and every generated page "
      "offline from the records and the caches; `make all` refreshes the caches "
      "first.")
    A("")
    A("Citation counts are OpenAlex's count for the record's own primary paper, a "
      "rough popularity signal and not a quality measure. A paper claimed as "
      "primary by three or more records is a suite paper, and no count is shown.")
    A("")
    A("`make scview-import` and `make scview-proposal` are maintainer tooling: they "
      "compare the catalog with a local checkout of "
      "[scView](https://github.com/thirtysix/scView) and need its research files "
      "and a hand-written map that are not in either repository. Nothing else "
      "depends on them.")
    A("")
    A("## Licence")
    A("")
    A("Pipeline code: MIT ([LICENSE](LICENSE)). Catalog data, records and review "
      "chapters: CC BY 4.0 ([LICENSE-DATA](LICENSE-DATA)). To cite the catalog, see "
      "[CITATION.cff](CITATION.cff).")
    A("")
    return "\n".join(out)


def render_records_md(catalog: dict) -> str:
    """docs/records.md: every record once, under its primary category, with an
    anchor named by its id, so a record link resolves on GitHub."""
    records = catalog.get("records") or []
    by_id = {t["id"]: t for t in records}
    by_cat: dict[str, list] = {k: [] for k in CATEGORY_KEYS}
    for t in records:
        by_cat.setdefault(t["categories"][0], []).append(t)
    out = [f"# {TITLE}: all records", "",
           f"Every record in the catalog ({plural(len(records), 'record')}, built "
           f"{catalog['meta']['generated']}), once each, under its primary category. "
           "Generated by `pipeline/render.py`; the [README](../README.md) shows the "
           "top entries per category.", ""]
    for layer in LAYERS:
        keys = [k for k in CATEGORY_KEYS if CATEGORY_LAYER[k] == layer and by_cat[k]]
        if not keys:
            continue
        out += [f"## {layer_title(layer)[0]}", ""]
        for key in keys:
            out += [f"### {CATEGORY_LABEL[key]}", ""]
            for t in sorted(by_cat[key], key=top_order):
                out.extend(tool_line(t, by_id, base="", anchor=True))
            out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Review chapters
# ---------------------------------------------------------------------------
def review_parts(review: str) -> tuple[str, str]:
    chapter, _, anchor = (review or "").partition("#")
    return chapter.removesuffix(".md"), anchor


def chapter_table(rows: list[dict], records: dict | None = None) -> str:
    """The Markdown table a review chapter carries between its markers."""
    if not rows:
        return "_No records point at this chapter yet._"
    out = ["| Record | Kind | Tier | Side | Recovers / gain | Requires | Paper |",
           "| --- | --- | --- | --- | --- | --- | --- |"]
    # Tier, then name: not citations, which move on every enrichment and would
    # rewrite a hand-maintained chapter for no reason a reader cares about.
    for t in sorted(rows, key=lambda t: (tier_rank(t), t["name"].lower())):
        _, anchor = review_parts(t.get("review") or "")
        name = cell(t["name"])
        name = f"[{name}](#{anchor})" if anchor else name
        rg = " / ".join(x for x in (t.get("recovers", "").rstrip("."), gain_text(t)) if x)
        rg = md_refs(rg, records, "../records.md") if records else rg
        paper = ""
        if t.get("publication_url"):
            label = "preprint" if t.get("publication_is_preprint") else "paper"
            paper = f"[{label}]({t['publication_url']})"
            if t.get("year"):
                paper += f" {t['year']}"
        out.append(f"| {name} | {t['kind']} | `{t['tier']}` | {t['side']} | "
                   f"{cell(rg) or '-'} | {cell(', '.join(t.get('requires') or [])) or '-'} | "
                   f"{paper or '-'} |")
    return "\n".join(out)


def fill_markers(text: str, table: str) -> str | None:
    """Replace what sits between each start/end marker pair, and nothing else.

    Returns None, so the caller leaves the file alone, when the markers are not
    balanced pairs: rewriting a chapter whose end marker is missing would
    swallow everything after the start marker.
    """
    starts = [m.start() for m in MARK_START.finditer(text)]
    ends = [m.start() for m in MARK_END.finditer(text)]
    if not starts or len(starts) != len(ends):
        return None
    pairs = list(zip(starts, ends))
    if any(s > e for s, e in pairs) or any(pairs[i][1] > pairs[i + 1][0]
                                           for i in range(len(pairs) - 1)):
        return None
    return REGION.sub(lambda m: f"{m.group(1)}\n\n{table}\n\n{m.group(3)}", text)


def render_review(catalog: dict, review_dir: Path) -> list[tuple[Path, str]]:
    """Fill every chapter that carries markers. Returns [(path, outcome)]."""
    review_dir = Path(review_dir)
    if not review_dir.is_dir():
        return []
    by_chapter: dict[str, list] = {}
    by_id = {t["id"]: t for t in catalog.get("records") or []}
    for t in catalog.get("records") or []:
        chapter, _ = review_parts(t.get("review") or "")
        if chapter:
            by_chapter.setdefault(chapter, []).append(t)
    results = []
    for path in sorted(review_dir.glob("*.md")):
        text = path.read_text()
        if not MARK_START.search(text) and not MARK_END.search(text):
            continue
        new = fill_markers(text, chapter_table(by_chapter.get(path.stem, []), by_id))
        if new is None:
            results.append((path, "skipped: unbalanced records markers"))
        elif new != text:
            path.write_text(new)
            results.append((path, f"{len(by_chapter.get(path.stem, []))} records"))
        else:
            results.append((path, "unchanged"))
    return results


# ---------------------------------------------------------------------------
# Site
# ---------------------------------------------------------------------------
# The catalog explorer (filters, category chips, statistics panels, sortable
# table) is shared by the site (docs/index.html) and the hub page
# (dist/hub.html). Each piece below is dropped into both pages; only the
# surrounding page differs.
CATALOG_FILTERS = r"""    <input type="search" id="q" placeholder="Search name, summary, gain, caveats, tags…" autocomplete="off">
    <select id="layer" aria-label="Layer"><option value="">Any layer</option></select>
    <select id="kind" aria-label="Kind"><option value="">Any kind</option></select>
    <select id="tier" aria-label="Tier"><option value="">Any tier</option></select>
    <select id="side" aria-label="Side"><option value="">Any side</option></select>
    <select id="requires" aria-label="Requires"><option value="">Any input</option></select>
    <button class="theme" id="stats-toggle" type="button" aria-expanded="true">Hide stats</button>
"""

CATALOG_TABLE = r"""  <div id="cats"></div>
  <section class="stats" id="stats"><div class="panels" id="panels"></div></section>
  <div class="count" id="count"></div>
  <div class="tablewrap">
    <table>
      <thead>
      <tr>
        <th data-k="name">Name</th>
        <th data-k="categories">Categories</th>
        <th data-k="kind">Kind</th>
        <th data-k="tier_rank">Tier</th>
        <th data-k="side">Side</th>
        <th data-k="recovers">Recovers / gain</th>
        <th data-k="requires">Requires</th>
        <th data-k="year" class="num">Year</th>
        <th data-k="citations" class="num">Citations</th>
        <th data-k="n_links">Links</th>
      </tr>
      <tr class="filters">
        <th><input data-f="name" type="search" placeholder="filter…"></th>
        <th><input data-f="categories" type="search" placeholder="filter…"></th>
        <th></th><th></th><th></th>
        <th><input data-f="recovers" type="search" placeholder="filter…"></th>
        <th></th>
        <th><input data-f="year" type="number" min="1980" placeholder="min"></th>
        <th><input data-f="citations" type="number" min="0" placeholder="min"></th>
        <th></th>
      </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
  </div>
"""

CATALOG_NOTES = r"""    Every entry is a hand-written record validated against the hub's schema. A
    <span class="ok">✓</span> beside a paper means its DOI or PMID was fetched and the
    returned title matched the record; a <span class="bad">!</span> means the last
    citation check contradicted it. Citation counts are OpenAlex's count for the record's
    own primary paper: a rough popularity signal, not a quality measure. Categories with a
    dashed border belong to the adjacent concept map rather than to QC proper. Gains are
    labelled with who measured them (independent or self-reported).
"""

CATALOG_JS = r"""const VOCAB = __VOCAB__;
const STANDALONE = __STANDALONE__;
const BUILD_DATE = '__DATE__';
const root = document.documentElement;
document.getElementById('theme').onclick = () => {
  const cur = root.getAttribute('data-theme') ||
    (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  root.setAttribute('data-theme', cur === 'dark' ? 'light' : 'dark');
};

const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
// Record text can cite other records as [[id]]; the hub page links them.
const prose = s => STANDALONE ? hubRefs(esc(s)) : esc(s);
const catLabel = Object.fromEntries(VOCAB.categories.map(c => [c[0], c[1]]));
const catLayer = Object.fromEntries(VOCAB.categories.map(c => [c[0], c[2]]));
const catDesc = Object.fromEntries(VOCAB.categories.map(c => [c[0], c[3]]));
const tierOrder = VOCAB.tiers.map(t => t[0]);
const tierDesc = Object.fromEntries(VOCAB.tiers);
const benchById = Object.fromEntries((typeof BENCHMARKS !== 'undefined' ? BENCHMARKS : []).map(b => [b.id, b]));
const state = { q:'', cats:new Set(), layer:'', kind:'', tier:'', side:'', requires:'', col:{},
                sort:'citations', dir:-1 };
let visible = [];

// Filters can be preset from the URL: ?category=ambient-rna&tier=standard
const params = new URLSearchParams(location.search);
if (params.get('category')) params.get('category').split(',').forEach(c => state.cats.add(c));
['layer','kind','tier','side','requires'].forEach(k => { if (params.get(k)) state[k] = params.get(k); });

const fill = (id, pairs) => {
  const el = $(id);
  pairs.forEach(([v, label, title]) => {
    const o = document.createElement('option'); o.value = v; o.textContent = label || v;
    if (title) o.title = title;
    el.append(o);
  });
  el.value = state[id] || '';
};
fill('layer', VOCAB.layers.map(([k, head, desc]) => [k, head, desc]));
fill('kind', VOCAB.kinds.map(([k, d]) => [k, k, d]));
fill('tier', VOCAB.tiers.map(([k, d]) => [k, k, d]));
fill('side', VOCAB.sides.map(([k, d]) => [k, k, d]));
fill('requires', VOCAB.requires.map(([k, d]) => [k, k, d]));

// Derived once. Sorting the Links column means "which rows have links".
RECORDS.forEach(t => {
  t.tier_rank = tierOrder.indexOf(t.tier);
  t.n_links = (t.url ? 1 : 0) + (t.repo_url ? 1 : 0) + (t.publication_url ? 1 : 0);
});

// Category chips, one rack per layer, in schema order: the order is the QC
// pipeline's own, which says more than sorting by size would.
const catCounts = {};
RECORDS.forEach(t => t.categories.forEach(c => catCounts[c] = (catCounts[c] || 0) + 1));
function renderChips() {
  const box = $('cats'); box.innerHTML = '';
  VOCAB.layers.forEach(([layer, head]) => {
    if (state.layer && state.layer !== layer) return;
    const cats = VOCAB.categories.filter(c => c[2] === layer && catCounts[c[0]]);
    if (!cats.length) return;
    const h = document.createElement('div'); h.className = 'layerhead'; h.textContent = head;
    const rack = document.createElement('div'); rack.className = 'chips';
    cats.forEach(([key, label, lay, desc]) => {
      const b = document.createElement('button');
      b.className = 'chip' + (lay === 'adjacent' ? ' adj' : ''); b.type = 'button';
      b.dataset.tip = '<b>' + esc(label) + '</b>: ' + esc(desc) + tipNote(catCounts[key] + ' records' +
        (lay === 'adjacent' ? ', adjacent concept map' : '') + '. Click to filter; with several selected, ' +
        'a row needs any one of them.');
      b.setAttribute('aria-pressed', state.cats.has(key));
      b.innerHTML = '<span class="lab">' + esc(label) + '</span><span class="n">' + catCounts[key] + '</span>';
      b.onclick = () => {
        state.cats.has(key) ? state.cats.delete(key) : state.cats.add(key);
        b.setAttribute('aria-pressed', state.cats.has(key));
        render();
      };
      rack.append(b);
    });
    box.append(h, rack);
  });
}

const YEAR_MS = 365.25 * 24 * 3600 * 1000;
const matches = t => {
  if (state.cats.size && !t.categories.some(c => state.cats.has(c))) return false;
  if (state.layer && t.layer !== state.layer) return false;
  if (state.kind && t.kind !== state.kind) return false;
  if (state.tier && t.tier !== state.tier) return false;
  if (state.side && t.side !== state.side) return false;
  if (state.requires && !(t.requires || []).includes(state.requires)) return false;
  for (const [k, v] of Object.entries(state.col)) {
    if (v === '' || v === undefined) continue;
    if (k === 'name') {
      if (!(t.name + ' ' + t.summary).toLowerCase().includes(v)) return false;
    } else if (k === 'categories') {
      if (!t.categories.map(c => catLabel[c] || c).join(' ').toLowerCase().includes(v)) return false;
    } else if (k === 'recovers') {
      if (!((t.recovers || '') + ' ' + (t.gain || '')).toLowerCase().includes(v)) return false;
    } else {
      const n = Number(t[k]);
      if (!Number.isFinite(n) || n < Number(v)) return false;
    }
  }
  if (state.q) {
    const hay = [t.name, t.summary, t.recovers, t.gain, t.caveats, t.kind, t.tier, t.side,
      t.language, (t.tags || []).join(' '), (t.requires || []).join(' '),
      t.categories.map(c => catLabel[c] || c).join(' ')].join(' ').toLowerCase();
    if (!state.q.split(/\s+/).every(w => hay.includes(w))) return false;
  }
  return true;
};

const cmp = (a, b) => {
  const k = state.sort;
  let x = a[k], y = b[k];
  if (Array.isArray(x)) { x = x.join(); y = (y || []).join(); }
  if (k === 'year') { x = parseInt(x, 10); y = parseInt(y, 10); if (isNaN(x)) x = null; if (isNaN(y)) y = null; }
  if (x === null || x === undefined || x === '') return 1;
  if (y === null || y === undefined || y === '') return -1;
  if (typeof x === 'number' && typeof y === 'number') return (x - y) * state.dir;
  return String(x).localeCompare(String(y)) * state.dir;
};

// ---------------------------------------------------------------------------
// Statistics panel: each panel is one number and the distribution behind it,
// for whatever is currently filtered. One hue throughout, so bar length carries
// the magnitude and colour is not a second encoding of the same thing.
// ---------------------------------------------------------------------------
let statsOpen = true;
// One tooltip for the whole page: any element with data-tip (escaped HTML)
// shows it beside the pointer on hover, or below the element on keyboard focus.
const tip = $('tip');
let tipEl = null;
const placeTip = (cx, cy) => {
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let x = cx + pad, y = cy + pad;
  if (x + w > innerWidth - 8) x = Math.max(8, cx - w - pad);
  if (y + h > innerHeight - 8) y = Math.max(8, cy - h - pad);
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
};
const openTip = (el, cx, cy) => {
  tipEl = el; tip.innerHTML = el.dataset.tip; tip.style.opacity = '1'; placeTip(cx, cy);
};
const hideTip = () => { tipEl = null; tip.style.opacity = '0'; };
const tipTarget = e => (e.target.closest ? e.target.closest('[data-tip]') : null);
document.addEventListener('mouseover', e => {
  const el = tipTarget(e);
  if (!el) { if (tipEl) hideTip(); return; }
  if (el !== tipEl) openTip(el, e.clientX, e.clientY);
});
document.addEventListener('mousemove', e => { if (tipEl) placeTip(e.clientX, e.clientY); });
document.addEventListener('focusin', e => {
  const el = tipTarget(e);
  if (!el) { hideTip(); return; }
  const r = el.getBoundingClientRect();
  openTip(el, r.left, r.bottom - 6);
});
document.addEventListener('focusout', hideTip);
document.addEventListener('keydown', e => { if (e.key === 'Escape') hideTip(); });
addEventListener('scroll', () => { if (tipEl && !tipEl.contains(document.activeElement)) hideTip(); }, { passive: true });

// Tooltip text for the controls and column headers, built from the schema's vocabulary.
const tipList = pairs => '<ul>' + pairs.map(([k, d]) => '<li><b>' + esc(k) + '</b>: ' + esc(d) + '</li>').join('') + '</ul>';
const tipNote = s => '<span class="tl">' + s + '</span>';
const vocabDesc = (list, key) => ((list.find(x => x[0] === key) || [])[1] || '');
const SORT_NOTE = tipNote('Click to sort; click again to reverse the order.');
const HEAD_TIPS = {
  name: '<b>Name</b>: the tool, method, study, design or concept, with a one-line summary. ' +
    'Select a name to open the record: evidence, caveats, citation and where the review discusses it.',
  categories: '<b>Categories</b>: the QC or analysis stages the record belongs to. The first is its ' +
    'primary category. A dashed chip belongs to the adjacent concept map rather than to QC proper.',
  kind: '<b>Kind</b>: what sort of record it is.' + tipList(VOCAB.kinds),
  tier_rank: '<b>Tier</b>: how strong the evidence behind it is, strongest first.' + tipList(VOCAB.tiers) +
    tipNote("A method paper's comparison with its own competitors does not count as a benchmark."),
  side: '<b>Side</b>: what it does to the cells.' + tipList(VOCAB.sides),
  recovers: '<b>Recovers / gain</b>: what it salvages or improves, then the reported gain with its number ' +
    'and setting. The label in brackets says who measured the gain.' + tipList(VOCAB.gain_sources),
  requires: '<b>Requires</b>: the data it needs as input. Hover a chip for what each input means; ' +
    'the "Any input" filter above keeps records that need one of them.',
  year: '<b>Year</b>: publication year of the primary paper. The box below keeps records from that year on.',
  citations: "<b>Citations</b>: OpenAlex's count for the record's own primary paper, a rough popularity signal " +
    'and not a quality measure. A small second figure is the total across all of the record\'s papers. ' +
    'A paper claimed by three or more records is a suite paper and shows no count. The box below sets a minimum.',
  n_links: '<b>Links</b>: the site, code and paper or preprint (<span class="ok">✓</span> identifier fetched and ' +
    'title matched; <span class="bad">!</span> the last citation check contradicted it), and review: where ' +
    'a chapter discusses the record. Sorting puts records with more links first.',
};
const FILTER_TIPS = {
  name: 'Keep rows whose name or summary contains this text.',
  categories: 'Keep rows whose category names contain this text.',
  recovers: 'Keep rows whose recovers or gain text contains this.',
  year: 'Earliest publication year to keep.',
  citations: 'Minimum citation count to keep. Rows without a count drop out.',
};
const CONTROL_TIPS = {
  q: '<b>Search</b> every field: name, summary, recovers, gain, caveats, kind, tier, side, language, ' +
     'tags, required inputs and categories. With several words, a row must match all of them.',
  layer: '<b>Layer</b>' + tipList(VOCAB.layers.map(([k, head, desc]) => [head, desc])),
  kind: '<b>Kind</b>' + tipList(VOCAB.kinds),
  tier: '<b>Tier</b>' + tipList(VOCAB.tiers),
  side: '<b>Side</b>' + tipList(VOCAB.sides),
  requires: '<b>Required input</b>: keep records that need this kind of data.' + tipList(VOCAB.requires),
  'stats-toggle': 'Show or hide the summary panels. They always describe the rows currently shown.',
};
document.querySelectorAll('th[data-k]').forEach(th => {
  if (HEAD_TIPS[th.dataset.k]) th.dataset.tip = HEAD_TIPS[th.dataset.k] + SORT_NOTE;
});
document.querySelectorAll('[data-f]').forEach(el => { if (FILTER_TIPS[el.dataset.f]) el.dataset.tip = FILTER_TIPS[el.dataset.f]; });
Object.entries(CONTROL_TIPS).forEach(([id, html]) => { if ($(id)) $(id).dataset.tip = html; });
const compact = n => n >= 1000 ? (n / 1000).toFixed(n >= 10000 ? 0 : 1) + 'k' : String(n);

function columns(bins, width, height) {
  const padL = 30, padR = 6, padT = 12, padB = 17;
  const plotW = Math.max(40, width - padL - padR), plotH = height - padT - padB;
  const max = Math.max(1, ...bins.map(b => b.value));
  const band = plotW / bins.length;
  const barW = Math.max(2, Math.min(24, band - 2));
  const y = v => padT + plotH - (v / max) * plotH;
  const parts = [];
  for (const v of [0, max]) {
    parts.push('<line x1="' + padL + '" x2="' + (padL + plotW) + '" y1="' + y(v) + '" y2="' + y(v) +
               '" stroke="var(--grid)" stroke-width="1"/>');
    parts.push('<text x="' + (padL - 5) + '" y="' + (y(v) + 3.5) +
               '" text-anchor="end" font-size="9.5" fill="var(--muted)">' + compact(v) + '</text>');
  }
  const peak = bins.reduce((a, b) => b.value > a.value ? b : a, bins[0]);
  bins.forEach((b, i) => {
    const x = padL + i * band + (band - barW) / 2;
    const top = y(b.value), h = padT + plotH - top;
    if (h > 0) {
      const r = Math.min(4, barW / 2, h);
      parts.push('<path d="M' + x + ',' + (padT + plotH) + ' L' + x + ',' + (top + r) +
                 ' Q' + x + ',' + top + ' ' + (x + r) + ',' + top + ' L' + (x + barW - r) + ',' + top +
                 ' Q' + (x + barW) + ',' + top + ' ' + (x + barW) + ',' + (top + r) +
                 ' L' + (x + barW) + ',' + (padT + plotH) + ' Z" fill="var(--series-1)"/>');
    }
    if (b === peak && b.value > 0 && barW >= 14) {
      parts.push('<text x="' + (x + barW / 2) + '" y="' + (top - 3) +
                 '" text-anchor="middle" font-size="9.5" font-weight="600" fill="var(--fg)">' +
                 compact(b.value) + '</text>');
    }
    if (b.tick) {
      parts.push('<text x="' + (x + barW / 2) + '" y="' + (height - 4) +
                 '" text-anchor="middle" font-size="9.5" fill="var(--muted)">' + esc(b.tick) + '</text>');
    }
    parts.push('<rect class="band" x="' + (padL + i * band) + '" y="' + padT + '" width="' + band +
               '" height="' + plotH + '" fill="transparent" data-tip="' + esc(b.tip) + '"/>');
  });
  return '<svg viewBox="0 0 ' + width + ' ' + height + '" width="' + width + '" height="' + height +
         '" role="img">' + parts.join('') + '</svg>';
}

const KPI_TIPS = {
  'Records shown': 'Records matching the current search, filters and categories.',
  'Keep or recover cells': 'Records whose side is additive (keeps or recovers cells, or gets more signal ' +
    'from the cells kept) or both.',
  'Independently measured gain': "Records whose reported gain was measured by other authors, in a benchmark " +
    "or independent study, rather than by the method's own authors.",
  'With a verified paper': 'Records whose DOI or PMID was fetched and whose title matched the record. ' +
    'The smaller figure counts records with any paper.',
  'Actively maintained': 'Records whose repository was updated in the last two years and is not archived, ' +
    'out of those with repository data.',
};
function panel(stat, chart, width) {
  const kt = KPI_TIPS[stat[0]] ? ' data-tip="' + esc(KPI_TIPS[stat[0]]) + '"' : '';
  return '<div class="panel"><div class="kpi"' + kt + '><div class="k">' + esc(stat[0]) + '</div>' +
    '<div class="v">' + esc(stat[1]) + '</div><div class="s">' + esc(stat[2]) + '</div></div>' +
    (chart ? '<div class="chart"><h3>' + esc(chart.title) + '</h3><p>' + esc(chart.sub) + '</p>' +
             columns(chart.bins, width, 120) + '</div>' : '') + '</div>';
}

// Nominal bins in vocabulary order, with short ticks and the full name in the tooltip.
const nominalBins = (rows, key, order) => {
  if (!rows.length) return null;
  return { bins: order.map(v => {
    const n = rows.filter(t => t[key] === v).length;
    const tick = v.length > 11 ? v.split('-').map(p => p[0]).join('').toUpperCase() : v;
    return { value: n, tick, tip: '<b>' + esc(v) + '</b> ' + n + ' records' };
  }), n: rows.length };
};
const yearBins = (rows, key) => {
  const years = rows.map(t => parseInt(t[key], 10)).filter(y => y >= 1990 && y <= 2100);
  if (!years.length) return null;
  const lo = Math.min(...years), hi = Math.max(...years);
  const counts = new Map();
  years.forEach(y => counts.set(y, (counts.get(y) || 0) + 1));
  const bins = [];
  for (let y = lo; y <= hi; y++) {
    const n = counts.get(y) || 0;
    bins.push({ value: n, tick: (y % 5 === 0 || lo === hi) ? String(y) : '',
                tip: '<b>' + y + '</b> ' + n + ' records' });
  }
  return { bins, n: years.length };
};
const LOG_BUCKETS = [[0, 0, 'none'], [1, 9, '1-9'], [10, 99, '10-99'], [100, 999, '100-999'],
                     [1000, 9999, '1k-10k'], [10000, Infinity, '10k+']];
const logBins = (rows, key) => {
  const vals = rows.map(t => t[key]).filter(v => v !== null && v !== undefined && v !== '');
  if (!vals.length) return null;
  return { bins: LOG_BUCKETS.map(([lo, hi, tick]) => {
    const n = vals.filter(v => v >= lo && v <= hi).length;
    return { value: n, tick, tip: '<b>' + tick + '</b> ' + n + ' records' };
  }), n: vals.length };
};

function renderStats(rows) {
  const total = rows.length;
  const pct = n => total ? Math.round(100 * n / total) + '%' : '0%';
  const box = $('panels');
  const cols = Math.max(1, Math.floor((box.clientWidth + 10) / 270));
  const w = Math.max(220, Math.floor((box.clientWidth - 10 * (cols - 1)) / cols) - 26);
  const additive = rows.filter(t => t.side === 'additive' || t.side === 'both').length;
  const independent = rows.filter(t => t.gain_source === 'independent').length;
  const withPub = rows.filter(t => t.publication).length;
  const checked = rows.filter(t => t.verified).length;
  const tracked = rows.filter(t => t.repo_pushed).length;
  const active = rows.filter(t => t.repo_pushed && !t.repo_archived &&
                                  (Date.now() - Date.parse(t.repo_pushed)) / YEAR_MS <= 2).length;
  const yb = yearBins(rows, 'year'), tb = nominalBins(rows, 'tier', tierOrder);
  const sb = nominalBins(rows, 'side', VOCAB.sides.map(s => s[0]));
  const cb = logBins(rows, 'citations');
  const pb = yearBins(rows.map(t => ({ y: (t.repo_pushed || '').slice(0, 4) })), 'y');
  const panels = [
    [['Records shown', total.toLocaleString(),
      total === RECORDS.length ? 'the whole catalog' : 'of ' + RECORDS.length + ' total'],
     yb && { title: 'By publication year', sub: yb.n + ' with a year', bins: yb.bins }],
    [['Keep or recover cells', additive.toLocaleString(), pct(additive) + ' are additive or both'],
     sb && { title: 'By side', sub: 'what the method does to the cells', bins: sb.bins }],
    [['Independently measured gain', independent.toLocaleString(), pct(independent) + ' of these'],
     tb && { title: 'By tier', sub: 'hover a bar for the tier name', bins: tb.bins }],
    [['With a verified paper', checked.toLocaleString(), withPub + ' with any paper'],
     cb && { title: 'Citations of the primary paper', sub: cb.n + ' with a count', bins: cb.bins }],
    [['Actively maintained', active.toLocaleString(),
      tracked ? Math.round(100 * active / tracked) + '% of ' + tracked + ' with repository data'
              : 'no repository data yet (make enrich)'],
     pb && { title: 'Repository last updated', sub: pb.n + ' with a live repository', bins: pb.bins }],
  ];
  box.innerHTML = panels.map(([s, c]) => panel(s, c, w)).join('');
}

// The site links to the chapter file; the hub page to the chapter on the same page.
function reviewHref(t) {
  if (STANDALONE) return hubReviewHref(t);
  if (!t.review) return '';
  const [chapter, anchor] = t.review.split('#');
  return 'review/' + chapter.replace(/\.md$/, '') + '.md' + (anchor ? '#' + anchor : '');
}

function render() {
  const rows = RECORDS.filter(matches).sort(cmp);
  visible = rows;
  renderChips();
  if (statsOpen) renderStats(rows);
  $('count').textContent = rows.length + ' of ' + RECORDS.length + ' records' +
    (state.cats.size ? ' · ' + [...state.cats].map(c => catLabel[c] || c).join(', ') : '');
  if (!RECORDS.length) {
    $('rows').innerHTML = '<tr><td colspan="10" class="empty">No records yet. They appear here after the next build.</td></tr>';
    return;
  }
  const dash = '<span class="no">-</span>';
  $('rows').innerHTML = rows.map(t => {
    const href = t.url || t.repo_url || t.publication_url || '';
    const cav = t.caveats ? ' <span class="cav" data-tip="' + esc('<b>Caveats</b>: ' + esc(t.caveats)) + '">caveats</span>' : '';
    // On the hub page the name opens the record's details; its links are in the details.
    const nameCell = (STANDALONE ? hubNameButton(t)
      : href ? '<a class="nm" href="' + esc(href) + '">' + esc(t.name) + '</a>'
             : '<span class="nm">' + esc(t.name) + '</span>') +
      (t.repo_archived ? ' <span class="arch" data-tip="The repository is archived: read-only, no longer maintained.">archived</span>' : '') +
      '<span class="sm">' + esc(t.summary) + cav + '</span>';
    const cats = t.categories.map((c, i) => '<span class="cat' + (catLayer[c] === 'adjacent' ? ' adj' : '') +
      '" data-tip="' + esc('<b>' + esc(catLabel[c] || c) + '</b>: ' + esc(catDesc[c] || '') +
        tipNote((i === 0 ? 'Primary category' : 'Secondary category') +
                (catLayer[c] === 'adjacent' ? ', adjacent concept map' : ''))) +
      '">' + esc(catLabel[c] || c) + '</span>').join('');
    const rank = t.tier_rank >= 0 ? Math.min(t.tier_rank, 4) : 4;
    const benches = (t.benchmark_refs || []).map(b =>
      '<a class="bm" href="' + esc(b.url) + '" data-tip="' + esc('<b>Independent benchmark</b>: ' + esc(b.name) +
        (b.scope ? tipNote(esc(b.scope)) : '')) + '">benchmarked: ' +
      esc(b.name.length > 28 ? b.name.slice(0, 27) + '…' : b.name) + '</a>').join('');
    const tierCell = '<span class="tier t' + rank + '" data-tip="' + esc('<b>' + esc(t.tier) + '</b>: ' + esc(tierDesc[t.tier] || '')) + '">' +
      esc(t.tier) + '</span>' + benches;
    let rg = '';
    if (t.recovers) rg += prose(t.recovers);
    if (t.gain) rg += (rg ? '<br>' : '') + '<b>Gain:</b> ' + prose(t.gain) +
      (t.gain_source && t.gain_source !== 'none' ? ' <span class="gs" data-tip="' +
        esc('<b>' + esc(t.gain_source) + '</b>: ' + esc(vocabDesc(VOCAB.gain_sources, t.gain_source))) + '">(' +
        esc(t.gain_source) + ')</span>' : '');
    const req = (t.requires || []).map(r => '<span class="req" data-tip="' +
      esc('<b>' + esc(r) + '</b>: ' + esc(vocabDesc(VOCAB.requires, r))) + '">' + esc(r) + '</span>').join('');
    let cites = t.citations != null ? t.citations.toLocaleString()
      : (t.citation_note ? '<span data-tip="' + esc(esc(t.citation_note)) + '">' + dash + '</span>' : dash);
    if (t.citations != null && t.citations_total && t.citations_papers)
      cites += '<span class="agg" data-tip="Citations summed across the record\'s own papers; the table sorts on the primary paper.">' +
               t.citations_total.toLocaleString() + ' / ' + t.citations_papers + 'p</span>';
    const links = [];
    if (t.site) links.push('<a href="' + esc(t.site) + '" data-tip="' + esc('Homepage: ' + esc(t.site)) + '">site</a>');
    if (t.repo_url) links.push('<a href="' + esc(t.repo_url) + '" data-tip="' + esc('Source code: ' + esc(t.repo_url) +
      (t.repo_stars ? tipNote(t.repo_stars.toLocaleString() + ' stars' + (t.repo_pushed ? ', last updated ' + esc(t.repo_pushed.slice(0, 10)) : '')) : '')) + '">code</a>');
    if (t.publication_url) {
      const ptip = [t.publication_title, t.publication_venue, t.year].filter(Boolean).join(' · ');
      let mark = '';
      if (t.citation_check === 'mismatch')
        mark = '<span class="bad" data-tip="The last citation check contradicted this record. See docs/citation-check.md.">!</span>';
      else if (t.verified)
        mark = '<span class="ok" data-tip="Verified: the DOI or PMID was fetched and its title matched the record.">✓</span>';
      links.push('<a href="' + esc(t.publication_url) + '" data-tip="' + esc(esc(ptip)) + '">' +
                 (t.publication_is_preprint ? 'preprint' : 'paper') + '</a>' + mark);
    }
    const rv = reviewHref(t);
    if (rv) links.push('<a href="' + esc(rv) + '" data-tip="Open the chapter passage that discusses this record.">review</a>');
    return (STANDALONE ? '<tr data-id="' + esc(t.id) + '">' : '<tr>') +
      '<td class="name">' + nameCell + '</td><td>' + cats + '</td>' +
      '<td><span data-tip="' + esc('<b>' + esc(t.kind) + '</b>: ' + esc(vocabDesc(VOCAB.kinds, t.kind))) + '">' + esc(t.kind) + '</span></td>' +
      '<td>' + tierCell + '</td>' +
      '<td><span data-tip="' + esc('<b>' + esc(t.side) + '</b>: ' + esc(vocabDesc(VOCAB.sides, t.side))) + '">' + esc(t.side) + '</span></td>' +
      '<td class="rg">' + (rg || dash) + '</td><td>' + (req || dash) + '</td>' +
      '<td class="num">' + esc(t.year) + '</td><td class="num">' + cites + '</td>' +
      '<td class="lnk">' + (links.join('') || dash) + '</td></tr>' +
      (STANDALONE ? hubDetailRow(t) : '');
  }).join('');
}

document.querySelectorAll('[data-f]').forEach(el => {
  const apply = () => {
    const v = el.value.trim();
    if (v === '') delete state.col[el.dataset.f];
    else state.col[el.dataset.f] = el.type === 'search' ? v.toLowerCase() : v;
    render();
  };
  // One debounce timer PER ELEMENT: a shared timer let editing one box cancel
  // another's pending update, leaving a cleared filter silently applied.
  let timer;
  el.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(apply, 120); });
  el.addEventListener('click', e => e.stopPropagation());
});
document.querySelectorAll('th[data-k]').forEach(th => {
  th.tabIndex = 0;
  th.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); th.click(); } });
  th.onclick = () => {
    const k = th.dataset.k;
    state.dir = state.sort === k ? -state.dir
      : (['name', 'categories', 'kind', 'side', 'recovers', 'requires', 'tier_rank'].includes(k) ? 1 : -1);
    state.sort = k;
    document.querySelectorAll('th .ar').forEach(a => a.remove());
    const ar = document.createElement('span');
    ar.className = 'ar'; ar.textContent = state.dir > 0 ? ' ▲' : ' ▼';
    th.append(ar);
    render();
  };
});
let qTimer;
$('q').oninput = e => { clearTimeout(qTimer); qTimer = setTimeout(() => { state.q = e.target.value.trim().toLowerCase(); render(); }, 120); };
['layer', 'kind', 'tier', 'side', 'requires'].forEach(id => $(id).onchange = e => {
  state[id] = e.target.value;
  if (id === 'layer') [...state.cats].forEach(c => { if (state.layer && catLayer[c] !== state.layer) state.cats.delete(c); });
  render();
});
$('stats-toggle').onclick = () => {
  statsOpen = !statsOpen;
  $('stats').style.display = statsOpen ? '' : 'none';
  $('stats-toggle').textContent = statsOpen ? 'Hide stats' : 'Show stats';
  $('stats-toggle').setAttribute('aria-expanded', String(statsOpen));
  if (statsOpen) render();
};
let rzTimer;
addEventListener('resize', () => {
  clearTimeout(rzTimer);
  rzTimer = setTimeout(() => { if (statsOpen) renderStats(RECORDS.filter(matches)); }, 150);
});
"""

# The site only: browsers save the file; the hub page is viewed where downloads are inert.
DOWNLOAD_JS = r"""// Download exactly what is on screen, tab-separated like data/catalog.tsv.
const DL_COLS = [
  ['id', t => t.id], ['name', t => t.name], ['kind', t => t.kind], ['layer', t => t.layer],
  ['categories', t => t.categories.join('; ')], ['tier', t => t.tier], ['side', t => t.side],
  ['summary', t => t.summary], ['recovers', t => t.recovers], ['gain', t => t.gain],
  ['gain_source', t => t.gain_source], ['requires', t => (t.requires || []).join('; ')],
  ['caveats', t => t.caveats], ['url', t => t.url], ['repository', t => t.repo_url],
  ['doi', t => t.doi], ['pmid', t => t.pmid], ['cite_title', t => t.cite_title],
  ['year', t => t.year], ['verified', t => t.verified ? 'yes' : 'no'],
  ['citations', t => t.citations], ['stars', t => t.repo_stars], ['last_push', t => t.repo_pushed],
  ['benchmarks', t => (t.benchmarks || []).join('; ')], ['review', t => t.review],
  ['tags', t => (t.tags || []).join('; ')],
];
const tsvCell = v => (v === null || v === undefined) ? '' : String(v).replace(/[\t\r\n]+/g, ' ').trim();
$('dl').onclick = () => {
  if (!visible.length) return;
  const lines = [DL_COLS.map(c => c[0]).join('\t')];
  for (const t of visible) lines.push(DL_COLS.map(c => tsvCell(c[1](t))).join('\t'));
  const bits = [];
  if (state.q) bits.push(state.q.replace(/[^a-z0-9]+/gi, '-'));
  if (state.cats.size) bits.push([...state.cats].join('-'));
  ['layer', 'kind', 'tier', 'side', 'requires'].forEach(k => { if (state[k]) bits.push(state[k]); });
  const stem = ['single-cell-qc', ...bits, visible.length + 'records'].join('_').replace(/_+/g, '_').slice(0, 120);
  const blob = new Blob(['﻿' + lines.join('\n') + '\n'], {type: 'text/tab-separated-values;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = stem + '.tsv';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
};
"""

def slim_records(catalog: dict) -> list[dict]:
    """What the page needs per record, without the fields only the TSV uses."""
    keep = ("id", "name", "kind", "layer", "categories", "side", "tier", "summary",
            "recovers", "gain", "gain_source", "requires", "caveats", "url", "repo_url",
            "language", "doi", "pmid", "cite_title", "year", "verified", "citation_check",
            "publication", "publication_url", "publication_is_preprint",
            "publication_title", "publication_venue", "citations", "citation_note",
            "citations_total", "citations_papers", "repo_stars", "repo_pushed",
            "repo_archived", "benchmarks", "benchmark_refs", "review", "tags")
    out = []
    for t in catalog.get("records") or []:
        row = {k: t.get(k) for k in keep}
        # Empty values cost bytes in a payload every visitor downloads.
        row = {k: v for k, v in row.items()
               if not (v is None or v is False or v == "" or v == [])
               or k in ("id", "name", "categories", "summary")}
        site = site_url(t)
        if site:
            row["site"] = site
        out.append(row)
    return out


def vocab() -> dict:
    return {
        "categories": [[k, CATEGORY_LABEL[k], CATEGORY_LAYER[k], CATEGORY_DESC[k]]
                       for k in CATEGORY_KEYS],
        "layers": [[k, *layer_title(k)] for k in LAYERS],
        "kinds": [[k, v] for k, v in KINDS.items()],
        "tiers": [[k, v] for k, v in TIERS.items()],
        "sides": [[k, v] for k, v in SIDES.items()],
        "requires": [[k, v] for k, v in REQUIRES.items()],
        "gain_sources": [[k, v] for k, v in GAIN_SOURCES.items()],
    }


def _js_json(obj) -> str:
    # `</` inside a string would end an inline <script> early.
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")


def catalog_js(catalog: dict) -> str:
    return ("const RECORDS = " + _js_json(slim_records(catalog)) + ";\n"
            "const BENCHMARKS = " + _js_json(catalog.get("benchmarks") or []) + ";\n")


def _fill_catalog(page: str, catalog: dict, standalone: bool) -> str:
    """Drop the shared catalog pieces into a page, then its vocabulary and counts."""
    for slot, piece in (("__FILTERS__", CATALOG_FILTERS), ("__TABLE__", CATALOG_TABLE),
                        ("__NOTES__", CATALOG_NOTES), ("__CATALOG_JS__", CATALOG_JS),
                        ("__DOWNLOAD_JS__", DOWNLOAD_JS)):
        page = page.replace(slot, piece.rstrip("\n"))
    return (page
            .replace("__VOCAB__", _js_json(vocab()))
            .replace("__STANDALONE__", "true" if standalone else "false")
            .replace("__COUNT__", str(len(catalog.get("records") or [])))
            .replace("__DATE__", catalog["meta"]["generated"]))


def write_site(catalog: dict, docs_dir: Path = DOCS,
               review_dir: Path = REVIEW_DIR) -> Path:
    """docs/index.html: the hub as a whole page, for GitHub Pages."""
    docs_dir = Path(docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    stale = docs_dir / "catalog.js"          # the old site's data file
    if stale.exists():
        stale.unlink()
    index = docs_dir / "index.html"
    index.write_text(render_site(catalog, review_dir))
    return index


# ---------------------------------------------------------------------------
# Hub page (dist/hub.html): the review chapters and the catalog in one file
# ---------------------------------------------------------------------------
# The page is published as a private claude.ai artifact, which wraps it in its
# own <!doctype html><head><body> skeleton. So it has no skeleton of its own,
# starts with its <title> (only the first 8 KB is scanned for one), loads
# nothing from anywhere, offers no downloads (they are inert there), and names
# its views with plain #tokens, the only fragments an artifact link passes on:
# overview, ch01..chNN, catalog, a record id, or the id of a heading.

PUBMED = "https://pubmed.ncbi.nlm.nih.gov/"
REPO_URL = "https://github.com/thirtysix/awesome-single-cell-qc"
SITE_URL = "https://thirtysix.github.io/awesome-single-cell-qc/"
HUB_DESCRIPTION = ("A catalog and review of single-cell QC and preprocessing tools, methods "
                   "and evidence, with an emphasis on salvaging cells and signal in "
                   "multiplexed experiments.")
# [[id]], [[id#anchor]], [[id|label]]: the forms check.py resolves.
RECORD_REF = re.compile(r"\[\[([^\[\]|#]+?)(?:#[^\[\]|]*)?(?:\|([^\[\]]*))?\]\]")
HASH_TOKEN = re.compile(r"^[A-Za-z0-9._~-]+$")
# Evidence and hypotheses are cited like references, by id; tools, methods and
# designs read as nouns in a sentence, so they are named.
REFERENCE_KINDS = ("evidence", "hypothesis")
RECORDS_SLOT = "\x00records\x00"
MAP_SLOT = "\x00conceptmap\x00"

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_HR = re.compile(r"^ {0,3}([-*_])(?:\s*\1){2,}\s*$")
_QUOTE = re.compile(r"^ {0,3}>(?: |$)")
_UL = re.compile(r"^( {0,3})([-*+])(?: +|$)")
# At most three digits, so a wrapped line that starts "25925576) ..." (the end
# of a PMID) is never read as an ordered list item.
_OL = re.compile(r"^( {0,3})(\d{1,3})[.)](?: +|$)")
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$")
_CODE_SPAN = re.compile(r"(`+)(.+?)\1")
_HTML_ANCHOR = re.compile(r'<a\s+(?:id|name)="([^"]+)"\s*>\s*</a>')
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_MD_LINK = re.compile(r"\[([^\[\]]+)\]\(\s*<?([^()\s<>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_AUTOLINK = re.compile(r"<(https?://[^\s<>]+)>")
_BARE_URL = re.compile(r"(?<![\w/=\"'])https://[^\s<>()\x00]*[^\s<>().,;:!?'\"\x00]")
_PMID = re.compile(r"\bPMID:?\s*(\d{5,9})\b")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_EM_STAR = re.compile(r"(?<![*\w])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![*\w])")
_EM_UNDER = re.compile(r"(?<![\w\x00])_(?=[^\s_])(.+?)(?<=[^\s_])_(?!\w)")
_SLOT = re.compile(r"\x00(\d+)\x00")


def _esc(text: str) -> str:
    return html.escape(str(text), quote=False)


def _attr(text: str) -> str:
    return html.escape(str(text), quote=True)


def _token_slug(text: str) -> str:
    """A heading or anchor as a hash token: ASCII letters, digits and hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _plain(md: str) -> str:
    """Markdown inline text without its markup, for titles and contents entries."""
    md = RECORD_REF.sub(lambda m: m.group(2) or m.group(1), _HTML_ANCHOR.sub("", md))
    return re.sub(r"[*`]", "", _MD_LINK.sub(r"\1", md)).strip()


def _list_marker(line: str) -> tuple[bool, int, int] | None:
    """(ordered, content column, start number) when the line opens a list item."""
    m = _UL.match(line)
    if m:
        return False, m.end(), 1
    m = _OL.match(line)
    if m:
        return True, m.end(), int(m.group(2))
    return None


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _cells(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", row)]


def ref_label(t: dict) -> tuple[str, bool]:
    """(link text, is it a citation key) for an [[id]] that gives no label."""
    if t.get("kind") in REFERENCE_KINDS:
        return t["id"], True
    short = re.sub(r"\s*\([^()]*\)\s*$", "", t["name"]).strip()
    return short or t["name"], False


def record_tip(t: dict) -> str:
    """Tooltip HTML for a record link: name, tier pill, summary."""
    return (f'<b>{_esc(t["name"])}</b> <span class="tier {tier_class(t)}">{_esc(t["tier"])}</span>'
            f'<br>{_esc(t["summary"])}')


def tier_class(t: dict) -> str:
    """t0..t4, the catalog engine's tier colour classes, in schema order."""
    return f"t{min(tier_rank(t), 4)}"


class ReviewPage:
    """One review chapter as HTML for the hub page.

    A small Markdown converter covering what the chapters use: headings,
    paragraphs, bold and italic, nested lists, pipe tables, links, code spans
    and fences, block quotes and rules. It also turns [[id]] into a link that
    opens the record in the catalog, "PMID 12345678" into a PubMed link, links
    to other chapter files into links to their views, and the records:start/end
    region into a compact table of the records that name this chapter. Every
    element id starts with the view's token, so ids never collide across views.
    """

    def __init__(self, token: str, records: dict, link_map: dict):
        self.token = token
        self.records = records          # id -> record
        self.link_map = link_map        # chapter file name -> view token
        self.title: str | None = None   # the first H1
        self.ids = {f"{token}-title", f"{token}-records"}
        self.toc: list[tuple[int, str, str]] = []   # (level, text, element id)
        self.mentions: dict[str, str] = {}  # record id -> id of its first [[id]] link
        self.listed: dict[str, str] = {}    # record id -> its row in the records table
        self.refs = 0                       # [[id]] links written in the prose

    def unique(self, base: str) -> str:
        eid, n = base, 2
        while eid in self.ids:
            eid, n = f"{base}-{n}", n + 1
        self.ids.add(eid)
        return eid

    def render(self, text: str, rows: list[dict]) -> str:
        text = REGION.sub(f"\n\n{RECORDS_SLOT}\n\n", text.replace("\r\n", "\n"))
        text = MAP_MARK.sub(f"\n\n{MAP_SLOT}\n\n", text)
        lines = [line.expandtabs(4) for line in text.split("\n")]
        body = "\n".join(b for b in self.blocks(lines, top=True) if b)
        if MAP_SLOT in body:
            body = body.replace(MAP_SLOT, self.concept_map())
        return body.replace(RECORDS_SLOT, self.records_section(rows))

    # -- blocks ------------------------------------------------------------
    def _table_start(self, lines: list[str], i: int) -> bool:
        return ("|" in lines[i] and i + 1 < len(lines) and "|" in lines[i + 1]
                and "-" in lines[i + 1] and bool(_TABLE_SEP.match(lines[i + 1])))

    def _interrupts(self, lines: list[str], i: int) -> bool:
        """Does this line end the paragraph above it?"""
        line = lines[i]
        if line.strip() in (RECORDS_SLOT, MAP_SLOT) or line.lstrip().startswith("<!--"):
            return True
        if _FENCE.match(line) or _HEADING.match(line) or _HR.match(line):
            return True
        marker = _list_marker(line)
        # A wrapped line can start with "2020. " or "- "; only "1." or a bullet
        # may start a list without a blank line before it.
        if marker and (not marker[0] or marker[2] == 1):
            return True
        return self._table_start(lines, i)

    def blocks(self, lines: list[str], top: bool = False) -> list[str]:
        out: list[str] = []
        i, n = 0, len(lines)
        while i < n:
            line, s = lines[i], lines[i].strip()
            if not s:
                i += 1
            elif top and s == RECORDS_SLOT:
                self.toc.append((2, "Records in this chapter", f"{self.token}-records"))
                out.append(RECORDS_SLOT)
                i += 1
            elif top and s == MAP_SLOT:
                self.ids.add(f"{self.token}-map")
                self.toc.append((2, "Concept map", f"{self.token}-map"))
                out.append(MAP_SLOT)
                i += 1
            elif s.startswith("<!--"):
                while i < n and "-->" not in lines[i]:
                    i += 1
                i += 1
            elif m := _FENCE.match(line):
                fence, body = m.group(1), []
                i += 1
                while i < n and not lines[i].strip().startswith(fence):
                    body.append(lines[i])
                    i += 1
                i += 1
                out.append(f"<pre><code>{_esc(chr(10).join(body))}</code></pre>")
            elif m := _HEADING.match(line):
                out.append(self.heading(len(m.group(1)), m.group(2)))
                i += 1
            elif _HR.match(line):
                out.append("<hr>")
                i += 1
            elif _QUOTE.match(line):
                body = []
                while i < n and _QUOTE.match(lines[i]):
                    body.append(_QUOTE.sub("", lines[i], count=1))
                    i += 1
                out.append("<blockquote>\n" + "\n".join(self.blocks(body)) + "\n</blockquote>")
            elif self._table_start(lines, i):
                i = self.table_block(lines, i, out)
            elif _list_marker(line):
                i = self.list_block(lines, i, out)
            else:
                body = [s]
                i += 1
                while i < n and lines[i].strip() and not self._interrupts(lines, i):
                    body.append(lines[i].strip())
                    i += 1
                out.append(f"<p>{self.inline(' '.join(body))}</p>")
        return out

    def heading(self, level: int, raw: str) -> str:
        if level == 1 and self.title is None:
            self.title = raw            # shown as the view's title, not repeated
            return ""
        level = max(level, 2)
        text = _plain(raw)
        eid = self.unique(f"{self.token}-{_token_slug(text) or 'section'}")
        if level <= 3:
            self.toc.append((level, text, eid))
        return f'<h{level} id="{eid}">{self.inline(raw)}</h{level}>'

    def table_block(self, lines: list[str], i: int, out: list[str]) -> int:
        head = _cells(lines[i])
        align = []
        for c in _cells(lines[i + 1]):
            right, left = c.endswith(":"), c.startswith(":")
            align.append(' class="c"' if left and right else ' class="r"' if right else "")
        align += [""] * (len(head) - len(align))
        i += 2
        rows = []
        while i < len(lines) and lines[i].strip() and "|" in lines[i]:
            rows.append((_cells(lines[i]) + [""] * len(head))[:len(head)])
            i += 1
        thead = "".join(f"<th{a}>{self.inline(c)}</th>" for c, a in zip(head, align))
        tbody = "\n".join("<tr>" + "".join(f"<td{a}>{self.inline(c)}</td>"
                                           for c, a in zip(r, align)) + "</tr>" for r in rows)
        out.append(f'<div class="tablewrap"><table class="md"><thead><tr>{thead}</tr></thead>'
                   f"<tbody>\n{tbody}\n</tbody></table></div>")
        return i

    def list_block(self, lines: list[str], i: int, out: list[str]) -> int:
        n = len(lines)
        ordered, _, start = _list_marker(lines[i])
        items, loose = [], False
        while i < n:
            marker = _list_marker(lines[i])
            if not marker or marker[0] != ordered:
                break
            col = marker[1]
            body = [lines[i][col:]]
            i += 1
            while i < n:
                line = lines[i]
                if not line.strip():
                    j = i
                    while j < n and not lines[j].strip():
                        j += 1
                    if j < n and _indent(lines[j]) >= col:      # the item goes on
                        body += [""] * (j - i)
                        i, loose = j, True
                        continue
                    break
                if _indent(line) >= col:
                    body.append(line[col:])
                elif _list_marker(line) or self._interrupts(lines, i):
                    break
                else:
                    body.append(line.strip())                    # lazy continuation
                i += 1
            items.append(body)
            j = i
            while j < n and not lines[j].strip():
                j += 1
            if j > i:
                nxt = _list_marker(lines[j]) if j < n else None
                if not nxt or nxt[0] != ordered:
                    break
                i, loose = j, True
        lis = []
        for body in items:
            inner = [b for b in self.blocks(body) if b]
            if not loose:
                inner = [b[3:-4] if b.startswith("<p>") and b.endswith("</p>") else b
                         for b in inner]
            lis.append("<li>" + "\n".join(inner) + "</li>")
        tag = "ol" if ordered else "ul"
        first = f' start="{start}"' if ordered and start != 1 else ""
        out.append(f"<{tag}{first}>\n" + "\n".join(lis) + f"\n</{tag}>")
        return i

    # -- inline ------------------------------------------------------------
    def inline(self, text: str) -> str:
        slots: list[str] = []

        def stash(fragment: str) -> str:
            slots.append(fragment)
            return f"\x00{len(slots) - 1}\x00"

        text = _COMMENT.sub("", text)
        text = _CODE_SPAN.sub(lambda m: stash(f"<code>{_esc(m.group(2).strip())}</code>"), text)
        text = _HTML_ANCHOR.sub(lambda m: stash(self.anchor(m.group(1))), text)
        text = RECORD_MD_LINK.sub(lambda m: stash(self.md_record_link(m.group(2), m.group(1))),
                                  text)
        text = RECORD_REF.sub(lambda m: stash(self.record_link(m.group(1).strip(), m.group(2))),
                              text)
        text = _MD_LINK.sub(lambda m: stash(self.link(m.group(2), self.emphasis(_esc(m.group(1))))),
                            text)
        text = _AUTOLINK.sub(lambda m: stash(self.link(m.group(1), _esc(m.group(1)))), text)
        text = _BARE_URL.sub(lambda m: stash(self.link(m.group(0), _esc(m.group(0)))), text)
        text = _esc(text)
        text = _PMID.sub(lambda m: stash(f'<a href="{PUBMED}{m.group(1)}/">{m.group(0)}</a>'), text)
        text = self.emphasis(text)
        while "\x00" in text:
            text = _SLOT.sub(lambda m: slots[int(m.group(1))], text)
        return text

    @staticmethod
    def emphasis(text: str) -> str:
        text = _BOLD.sub(r"<strong>\1</strong>", text)
        text = _EM_STAR.sub(r"<em>\1</em>", text)
        return _EM_UNDER.sub(r"<em>\1</em>", text)

    def anchor(self, name: str) -> str:
        return f'<span class="anchor" id="{self.unique(f"{self.token}-{_token_slug(name)}")}"></span>'

    def link(self, url: str, text_html: str) -> str:
        """A Markdown link. Links to other chapter files open that chapter's view."""
        if url.startswith(("https://", "http://")):
            href = url
        else:
            name, _, frag = url.partition("#")
            token = self.link_map.get(Path(name).name) if name else self.token
            if token is None:
                return text_html        # a file the page does not carry: keep the text
            href = f"#{token}-{_token_slug(frag)}" if _token_slug(frag) else f"#{token}"
        return f'<a href="{_attr(href)}">{text_html}</a>'

    def record_link(self, rid: str, label: str | None) -> str:
        t = self.records.get(rid)
        if t is None:                   # make check reports these
            return f'<span class="rec missing">{_esc(rid)}</span>'
        self.refs += 1
        text, key = (label.strip(), False) if label and label.strip() else ref_label(t)
        attrs = []
        if rid not in self.mentions:
            self.mentions[rid] = self.unique(f"{self.token}-m-{rid}")
            attrs.append(f'id="{self.mentions[rid]}"')
        attrs += [f'href="#{_attr(rid)}"', f'class="rec {tier_class(t)}{" key" if key else ""}"',
                  f'data-tip="{_attr(record_tip(t))}"']
        return f'<a {" ".join(attrs)}>{_esc(text)}</a>'

    def md_record_link(self, rid: str, label: str) -> str:
        """[label](../records.md#id): the default label reads as a bare [[id]],
        so evidence keeps its citation-key style."""
        t = self.records.get(rid)
        default = t is not None and label.strip() == ref_label(t)[0]
        return self.record_link(rid, None if default else label)

    # -- the concept map ---------------------------------------------------
    def concept_map(self) -> str:
        """The QC categories in the middle, the adjacent concepts either side
        (labelled by their category, since concept names run long), one edge
        per qc_links entry; below it the same links as a list, which is all a
        phone shows."""
        eid = f"{self.token}-map"
        adjacent = [k for k in CATEGORY_KEYS if CATEGORY_LAYER[k] == "adjacent"]
        concepts = sorted(
            (t for t in self.records.values() if t.get("kind") == "concept"),
            key=lambda t: (adjacent.index(t["categories"][0])
                           if t["categories"][0] in adjacent else len(adjacent),
                           t["name"].lower()))
        head = (f'<section class="cmap" aria-labelledby="{eid}">'
                f'<h2 id="{eid}">Concept map</h2>')
        linked = {link["category"] for t in concepts for link in t.get("qc_links") or []}
        qc = [k for k in CATEGORY_KEYS if k in linked]
        if not concepts or not qc:
            return head + '<p class="note">No concept records with qc_links yet.</p></section>'
        half = len(adjacent) // 2
        left = [t for t in concepts if t["categories"][0] in adjacent[:half]]
        right = [t for t in concepts if t not in left]

        W, row, top, nw, qw = 960, 34, 20, 196, 212
        H = top * 2 + row * max(len(qc), len(left), len(right))

        def ys(n: int) -> list[float]:
            step = (H - 2 * top) / max(n, 1)
            return [top + step * (i + 0.5) for i in range(n)]

        qy = dict(zip(qc, ys(len(qc))))
        qx0, qx1 = (W - qw) / 2, (W + qw) / 2
        pos = {}
        for side, col in (("l", left), ("r", right)):
            x0 = 24 if side == "l" else W - 24 - nw
            for t, y in zip(col, ys(len(col))):
                pos[t["id"]] = (side, x0, y)
        edges, nodes = [], []
        for t in concepts:
            side, x0, y = pos[t["id"]]
            for link in t.get("qc_links") or []:
                q = link["category"]
                if q not in qy:
                    continue
                xa = x0 + nw if side == "l" else x0
                xb = qx0 if side == "l" else qx1
                mid = (xa + xb) / 2
                edges.append(
                    f'<path class="e" data-c="{_attr(t["id"])}" data-q="{_attr(q)}" '
                    f'd="M{xa:.0f},{y:.0f} C{mid:.0f},{y:.0f} {mid:.0f},{qy[q]:.0f} '
                    f'{xb:.0f},{qy[q]:.0f}" data-tip="{_attr("<b>" + _esc(CATEGORY_LABEL[q]) + "</b>: " + _esc(link.get("effect") or ""))}"></path>')
            n = len(t.get("qc_links") or [])
            nodes.append(
                f'<a class="n c" href="#{_attr(t["id"])}" data-c="{_attr(t["id"])}" '
                f'aria-label="{_attr(t["name"])}" '
                f'data-tip="{_attr(record_tip(t) + "<span class=tl>" + plural(n, "QC link") + "</span>")}">'
                f'<rect x="{x0:.0f}" y="{y - 13:.0f}" width="{nw}" height="26" rx="6"/>'
                f'<text x="{x0 + nw / 2:.0f}" y="{y + 4.5:.0f}">'
                f'{_esc(CATEGORY_LABEL.get(t["categories"][0], t["name"]))}</text></a>')
        for q, y in qy.items():
            nodes.append(
                f'<g class="n q" tabindex="0" data-q="{_attr(q)}" aria-label="{_attr(CATEGORY_LABEL[q])}" '
                f'data-tip="{_attr("<b>" + _esc(CATEGORY_LABEL[q]) + "</b>: " + _esc(CATEGORY_DESC[q]))}">'
                f'<rect x="{qx0:.0f}" y="{y - 13:.0f}" width="{qw}" height="26" rx="13"/>'
                f'<text x="{W / 2:.0f}" y="{y + 4.5:.0f}">{_esc(CATEGORY_LABEL[q])}</text></g>')
        svg = (f'<svg class="cmap-svg" viewBox="0 0 {W} {H:.0f}" role="img" '
               f'aria-label="Which QC choices affect which downstream concepts">'
               + "".join(edges) + "".join(nodes) + "</svg>")
        items = []
        for t in concepts:
            lis = "".join(
                f'<li data-q="{_attr(link["category"])}"><strong>'
                f'{_esc(CATEGORY_LABEL.get(link["category"], link["category"]))}</strong>: '
                f'{self.inline(link.get("effect") or "")}</li>'
                for link in t.get("qc_links") or [])
            lid = self.unique(f"{self.token}-map-{t['id']}")
            self.mentions.setdefault(t["id"], lid)
            refs, link = self.refs, self.record_link(t["id"], None)
            self.refs = refs                # refs counts [[id]] written in the prose only
            items.append(f'<div class="cmap-c" data-c="{_attr(t["id"])}">'
                         f'<h3 id="{lid}">{link}</h3>'
                         f'<ul>{lis}</ul></div>')
        note = ('<p class="note">QC categories in the middle; adjacent concepts either side. '
                "Point at a node to trace its links, select a concept to open its record. "
                "Each link is one evidence-backed effect, listed below.</p>")
        return head + note + svg + '<div class="cmap-list">' + "".join(items) + "</div></section>"

    # -- the records:start/end region --------------------------------------
    def records_section(self, rows: list[dict]) -> str:
        eid = f"{self.token}-records"
        head = (f'<section class="records" aria-labelledby="{eid}">'
                f'<h2 id="{eid}">Records in this chapter</h2>')
        if not rows:
            return head + '<p class="note">No records point at this chapter yet.</p></section>'
        out = []
        # The order of the chapter's own Markdown table: tier, then name.
        for t in sorted(rows, key=lambda t: (tier_rank(t), t["name"].lower())):
            rid, cls = t["id"], tier_class(t)
            row_id = ""
            if rid not in self.mentions:
                self.listed[rid] = self.unique(f"{self.token}-m-{rid}")
                row_id = f' id="{self.listed[rid]}"'
            paper = '<span class="no">-</span>'
            if t.get("publication_url"):
                label = "preprint" if t.get("publication_is_preprint") else "paper"
                paper = f'<a href="{_attr(t["publication_url"])}">{label}</a>'
            out.append(
                f'<tr{row_id}><td class="name"><a class="rec {cls}" href="#{_attr(rid)}">'
                f'{_esc(t["name"])}</a><span class="sm">{_esc(t["summary"])}</span></td>'
                f'<td>{_esc(t["kind"])}</td><td><span class="tier {cls}" '
                f'data-tip="{_attr("<b>" + _esc(t["tier"]) + "</b>: " + _esc(TIERS.get(t["tier"], "")))}">{_esc(t["tier"])}</span></td>'
                f'<td>{_esc(t["side"])}</td><td class="sm-col">'
                f'{_esc(", ".join(t.get("requires") or [])) or "-"}</td>'
                f'<td class="num">{_esc(t.get("year") or "")}</td><td>{paper}</td></tr>')
        note = (f'<p class="note">{plural(len(rows), "record")} name this chapter as the place '
                "they are reviewed. Select a name to open the record in the catalog.</p>")
        return (head + note + '<div class="tablewrap"><table class="rt"><thead><tr>'
                "<th>Record</th><th>Kind</th><th>Tier</th><th>Side</th><th>Requires</th>"
                '<th class="num">Year</th><th>Paper</th></tr></thead><tbody>\n'
                + "\n".join(out) + "\n</tbody></table></div></section>")


@dataclass
class ReviewView:
    token: str          # overview, ch01, ...
    number: str         # "00", "01", ...
    stem: str           # file name without .md, as records name it in `review:`
    title: str
    short: str          # the title up to its first colon or semicolon
    html: str
    page: ReviewPage
    n_records: int      # records whose `review:` names this chapter


def view_token(path: Path) -> str:
    return "overview" if path.name.startswith("00-") else f"ch{path.name[:2]}"


def hub_views(catalog: dict, review_dir: Path = REVIEW_DIR) -> list[ReviewView]:
    """The overview and every chapter in `review_dir`, rendered, in file order."""
    review_dir = Path(review_dir)
    files = sorted(review_dir.glob("[0-9][0-9]-*.md")) if review_dir.is_dir() else []
    link_map: dict[str, str] = {}
    for path in files:
        token, n = view_token(path), 2
        while token in link_map.values():          # two files sharing a number
            token, n = f"{view_token(path)}-{n}", n + 1
        link_map[path.name] = token
    records = {t["id"]: t for t in catalog.get("records") or []}
    by_chapter: dict[str, list] = {}
    for t in records.values():
        chapter, _ = review_parts(t.get("review") or "")
        if chapter:
            by_chapter.setdefault(chapter, []).append(t)
    views = []
    for path in files:
        token = link_map[path.name]
        page = ReviewPage(token, records, link_map)
        body = page.render(path.read_text(), by_chapter.get(path.stem, []))
        title = _plain(page.title or path.stem)
        if token != "overview":
            title = re.sub(r"^\d+\.\s*", "", title)
        short = ("Overview" if token == "overview"
                 else re.split(r"[:;]", title, maxsplit=1)[0].strip() or title)
        views.append(ReviewView(token, path.name[:2], path.stem, title, short, body, page,
                                len(by_chapter.get(path.stem, []))))
    return views


def review_index(views: list[ReviewView], records: list[dict]) -> tuple[dict, dict]:
    """Where each record sits in the review, for the catalog's details.

    review_link: id -> [view, element id] for the chapter its `review:` names:
                 its first [[id]] there, else its `#anchor`, else its row in that
                 chapter's records table, else the chapter itself.
    cited_in:    id -> [[view, element id], ...] for every view whose text links it.
    """
    by_stem = {v.stem: v for v in views}
    cited: dict[str, list] = {}
    for v in views:
        for rid, eid in v.page.mentions.items():
            cited.setdefault(rid, []).append([v.token, eid])
    review_link: dict[str, list] = {}
    for t in records:
        chapter, anchor = review_parts(t.get("review") or "")
        v = by_stem.get(chapter)
        if v is None:
            continue
        anchor_id = f"{v.token}-{_token_slug(anchor)}" if _token_slug(anchor) else ""
        eid = (v.page.mentions.get(t["id"])
               or (anchor_id if anchor_id in v.page.ids else "")
               or v.page.listed.get(t["id"]) or v.token)
        review_link[t["id"]] = [v.token, eid]
    return review_link, cited


# Every colour on the hub page, light then dark. The CSS is written from these
# two dicts, so the bare :root block, the prefers-color-scheme block and the
# [data-theme="dark"] block cannot drift apart. Neutrals lean slightly toward
# the petrol accent; t0..t4 are the tiers in schema order (standard, benchmarked
# winner, benchmarked, published but untested, hypothesis).
HUB_LIGHT = {
    "bg": "#fafbfb", "surface": "#f0f4f4", "fg": "#152022", "muted": "#536063",
    "faint": "#7b8789", "line": "#d8e0e1", "line-strong": "#b5c2c3",
    "accent": "#0a6670", "accent-hover": "#074c54", "accent-soft": "#dcecee",
    "on-accent": "#ffffff", "mark": "#f9edbd", "warn": "#964e0e", "ok": "#1d6d42",
    "series-1": "#2b7f88", "grid": "#e0e7e8", "shadow": "rgba(16, 30, 32, 0.14)",
    "t0": "#e6eaf6", "t0-fg": "#313e77", "t0-line": "#8794cf",
    "t1": "#ddefe3", "t1-fg": "#195a33", "t1-line": "#5fae7f",
    "t2": "#f5ebcf", "t2-fg": "#694c0d", "t2-line": "#c69b3c",
    "t3": "#e9edee", "t3-fg": "#445154", "t3-line": "#9aa8aa",
    "t4": "#efe7f7", "t4-fg": "#603889", "t4-line": "#a784cf",
}
HUB_DARK = {
    "bg": "#0f1516", "surface": "#152022", "fg": "#e0e8e8", "muted": "#9babad",
    "faint": "#6f7d7f", "line": "#253132", "line-strong": "#3a494a",
    "accent": "#5cc0c8", "accent-hover": "#8ad5da", "accent-soft": "#15363a",
    "on-accent": "#08191b", "mark": "#3b3418", "warn": "#e5a66b", "ok": "#70d09b",
    "series-1": "#4aaeb6", "grid": "#213031", "shadow": "rgba(0, 0, 0, 0.5)",
    "t0": "#1d2747", "t0-fg": "#b6c3f2", "t0-line": "#6575b8",
    "t1": "#133423", "t1-fg": "#9cdab4", "t1-line": "#3f8f5f",
    "t2": "#382d11", "t2-fg": "#eac57a", "t2-line": "#a07c2c",
    "t3": "#212b2d", "t3-fg": "#b7c4c6", "t3-line": "#6c7b7d",
    "t4": "#2f2148", "t4-fg": "#d3b7f2", "t4-line": "#8a68b8",
}


def hub_theme_css() -> str:
    assert set(HUB_DARK) == set(HUB_LIGHT), "every colour needs a light and a dark value"
    light = "\n".join(f"  --{k}: {v};" for k, v in HUB_LIGHT.items())
    dark = "\n".join(f"  --{k}: {v};" for k, v in HUB_DARK.items())
    nested = dark.replace("\n", "\n  ")
    return ("/* Layout: a masthead, then a contents rail beside one view at a time (overview,\n"
            "   chapters, catalog). Chapter prose keeps a serif reading measure; tables and\n"
            "   the catalog use the full content width. Below 960px the rail becomes a\n"
            "   sticky strip of view links. */\n"
            f":root {{\n{light}\n{HUB_FONTS}}}\n"
            '@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {\n'
            f"  {nested}\n    color-scheme: dark;\n  }}\n}}\n"
            f':root[data-theme="dark"] {{\n{dark}\n  color-scheme: dark;\n}}\n')


HUB_FONTS = """\
  --font-text: Charter, "Bitstream Charter", "Sitka Text", Cambria, "Noto Serif", "DejaVu Serif", Georgia, serif;
  --font-ui: system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans", "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, "DejaVu Sans Mono", monospace;
  --measure: 96ch;
  --stick: 52px;
"""

HUB_CSS = r"""
*, *::before, *::after { box-sizing: border-box; }
[hidden] { display: none !important; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font: 15px/1.5 var(--font-ui);
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 0 64px;
  -webkit-text-size-adjust: 100%;
  text-size-adjust: 100%;
}
body::before {
  content: "";
  position: fixed;
  inset: 0 0 auto;
  height: env(safe-area-inset-top, 0px);
  background: var(--bg);
  z-index: 40;
}
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
a:hover { color: var(--accent-hover); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
[id], tr[data-id] { scroll-margin-top: calc(env(safe-area-inset-top, 0px) + var(--stick) + 16px); }
.frame { max-width: none; }

/* masthead */
.masthead {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 30rem);
  grid-template-areas: "title title" "id legend";
  gap: 8px 48px;
  padding-block: 20px 16px;
}
.masthead > * { min-width: 0; }
.titlerow { grid-area: title; display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.masthead .id { grid-area: id; }
.hub { margin: 0; font: 700 28px/1.15 var(--font-ui); letter-spacing: -0.02em; text-wrap: balance; }
.desc { margin: 0 0 12px; max-width: 60ch; font: 17px/1.5 var(--font-text); }
.meta { margin: 0 0 4px; color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }
.meta span + span::before { content: "\00B7"; margin-inline: 0.5em; color: var(--faint); }
.meta a { overflow-wrap: anywhere; }
.icon-btn {
  flex: none; display: inline-grid; place-items: center; width: 34px; height: 34px;
  border: 1px solid var(--line-strong); border-radius: 4px; background: var(--bg);
  color: var(--fg); cursor: pointer;
}
.icon-btn:hover { background: var(--surface); }
.legend { grid-area: legend; align-self: start; padding: 12px 14px; border: 1px solid var(--line); border-radius: 6px; background: var(--surface); }
.legend summary {
  cursor: pointer; color: var(--muted);
  font: 600 12px/1.4 var(--font-ui); letter-spacing: 0.08em; text-transform: uppercase;
}
.legend dl {
  display: grid; grid-template-columns: max-content 2.4em minmax(0, 1fr);
  gap: 7px 10px; align-items: baseline; margin: 10px 0 0; font-size: 13px; line-height: 1.4;
}
.legend .row { display: contents; }
.legend dt, .legend dd { margin: 0; min-width: 0; }
.legend .cnt { text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; }
.legend .mean { color: var(--muted); }
.legend-note { margin: 10px 0 0; color: var(--muted); font-size: 12.5px; }

/* tier pills: one class per tier, the same in the legend, chapters and catalog */
.tier {
  display: inline-block; padding: 1px 7px; border: 1px solid transparent; border-radius: 3px;
  font: 600 12px/1.5 var(--font-ui); white-space: nowrap;
}
.tier.t0 { background: var(--t0); color: var(--t0-fg); }
.tier.t1 { background: var(--t1); color: var(--t1-fg); }
.tier.t2 { background: var(--t2); color: var(--t2-fg); }
.tier.t3 { background: var(--t3); color: var(--t3-fg); }
.tier.t4 { background: var(--t4); color: var(--t4-fg); border-color: var(--t4-line); border-style: dashed; }

/* top bar: the catalog, then a menu of the chapters */
.layout { display: block; }
.topbar {
  position: sticky; top: env(safe-area-inset-top, 0px); z-index: 30;
  display: flex; align-items: center; gap: 6px; min-height: var(--stick);
  margin-bottom: 24px; border-block: 1px solid var(--line); background: var(--bg); font-size: 14px;
}
.topbar a.v, .chapters > summary {
  display: inline-flex; align-items: baseline; gap: 8px; padding: 6px 12px; border-radius: 4px;
  color: var(--fg); text-decoration: none; cursor: pointer; white-space: nowrap; line-height: 1.3;
}
.topbar a.v:hover, .chapters > summary:hover { background: var(--surface); }
.topbar a.v[aria-current="page"], .chapters.on > summary { background: var(--accent-soft); font-weight: 600; }
.topbar .n { color: var(--muted); font-size: 12px; font-weight: 400; font-variant-numeric: tabular-nums; }
.chapters { position: relative; min-width: 0; }
.chapters > summary { list-style: none; }
.chapters > summary::-webkit-details-marker { display: none; }
.chapters > summary::after { content: "\25BE"; color: var(--muted); }
.chapters .cur { overflow: hidden; text-overflow: ellipsis; color: var(--muted); font-weight: 400; }
.chapters .menu {
  position: absolute; top: calc(100% + 6px); left: 0; z-index: 35;
  width: min(26rem, calc(100vw - 32px)); max-height: 70vh; overflow-y: auto;
  margin: 0; padding: 6px; list-style: none;
  border: 1px solid var(--line); border-radius: 6px; background: var(--bg); box-shadow: 0 6px 24px var(--shadow);
}
.chapters .menu a {
  display: grid; grid-template-columns: 1.9em minmax(0, 1fr); gap: 6px; align-items: baseline;
  padding: 6px 8px; border-radius: 4px; color: var(--fg); text-decoration: none; line-height: 1.3;
}
.chapters .menu a:hover { background: var(--surface); }
.chapters .menu a[aria-current="page"] { background: var(--accent-soft); font-weight: 600; }
.chapters .num { color: var(--faint); font: 12px/1.3 var(--font-mono); font-variant-numeric: tabular-nums; }
.chapters .menu a[aria-current="page"] .num { color: var(--accent); }
.ch-toc { display: block; margin: 0 0 28px; padding: 12px 14px; border: 1px solid var(--line); border-radius: 6px; font-size: 14px; }
.ch-toc p { margin: 0 0 6px; color: var(--muted); font-size: 12px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
.ch-toc ol { margin: 0; padding: 0; list-style: none; }
.ch-toc li { padding: 2px 0; }
.ch-toc .h3 { padding-left: 14px; }
.ch-toc a { text-decoration: none; }
/* chapters read as a centred column; the catalog takes the full width */
.view:not(.catalog) { max-width: 68rem; margin-inline: auto; }

/* a view: eyebrow, title, standfirst, then prose or the catalog */
.view { min-width: 0; }
.view-head { max-width: 60rem; margin: 0 0 28px; }
.eyebrow {
  margin: 0 0 10px; color: var(--accent);
  font: 600 12px/1 var(--font-ui); letter-spacing: 0.1em; text-transform: uppercase;
}
.view-head h1 { margin: 0 0 10px; font: 600 32px/1.18 var(--font-text); letter-spacing: -0.01em; text-wrap: balance; }
.stand { margin: 0; color: var(--muted); font-size: 14px; font-variant-numeric: tabular-nums; }

.prose { font: 17px/1.62 var(--font-text); overflow-wrap: break-word; }
.prose > :where(p, ul, ol, h2, h3, h4, h5, h6, blockquote, pre, hr) { max-width: var(--measure); }
.prose p { margin: 0 0 1em; }
.prose ul, .prose ol { margin: 0 0 1em; padding-left: 1.4em; }
.prose li { margin: 0.3em 0; }
.prose li::marker { color: var(--faint); font-variant-numeric: tabular-nums; }
.prose h2 { margin: 2.1em 0 0.6em; font: 650 21px/1.3 var(--font-ui); letter-spacing: -0.01em; text-wrap: balance; }
.prose h3 { margin: 1.7em 0 0.5em; font: 650 17px/1.35 var(--font-ui); text-wrap: balance; }
.prose h4, .prose h5, .prose h6 { margin: 1.5em 0 0.4em; font: 650 15px/1.4 var(--font-ui); }
.prose strong { font-weight: 700; }
.prose code { padding: 0.1em 0.3em; border-radius: 3px; background: var(--surface); font: 0.84em var(--font-mono); }
.prose pre { overflow-x: auto; padding: 12px 14px; border-radius: 4px; background: var(--surface); font: 13px/1.5 var(--font-mono); }
.prose pre code { padding: 0; background: none; font: inherit; }
.prose blockquote { margin: 0 0 1em; padding-left: 14px; border-left: 2px solid var(--line-strong); color: var(--muted); }
.prose hr { margin: 2em 0; border: 0; border-top: 1px solid var(--line); }
.prose .tablewrap { margin: 1.2em 0 1.6em; }
.records { margin-top: 2.6em; }
/* concept map: QC in the middle, concepts either side; the list carries it on a phone */
.cmap { margin-top: 2.2em; }
.cmap-svg { display: block; width: 100%; height: auto; margin: 0.8em 0 1.4em; font: 12.5px var(--font-ui); }
.cmap-svg .e { fill: none; stroke: var(--line-strong); stroke-width: 1.4; transition: opacity .15s, stroke .15s; }
.cmap-svg .n rect { fill: var(--surface); stroke: var(--line-strong); }
.cmap-svg .n.q rect { fill: var(--accent-soft); stroke: var(--accent); }
.cmap-svg .n text { fill: var(--fg); text-anchor: middle; pointer-events: none; }
.cmap-svg .n { cursor: pointer; outline: none; }
.cmap-svg .n:focus-visible rect { stroke-width: 2.5; }
.cmap-svg.hl .e:not(.on) { opacity: 0.12; }
.cmap-svg.hl .n:not(.on) { opacity: 0.35; }
.cmap-svg .e.on { stroke: var(--accent); stroke-width: 2.2; }
.cmap-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 22em), 1fr)); gap: 0.4em 2em; }
.cmap-list h3 { margin: 0.9em 0 0.3em; }
.cmap-list ul { margin: 0; padding-left: 1.1em; font-size: 0.94em; }
.cmap-list li { margin: 0.25em 0; }
@media (max-width: 700px) { .cmap-svg { display: none; } }
.note { margin: 0 0 12px; color: var(--muted); font: 14px/1.5 var(--font-ui); }

/* record links in the text: underlined in the record's tier colour */
a.rec {
  color: inherit; text-decoration-line: underline; text-decoration-thickness: 2px;
  text-underline-offset: 0.22em; text-decoration-color: var(--t3-line);
  border-radius: 2px; transition: background-color 1.2s ease-out;
}
a.rec:hover { color: var(--accent); }
a.rec.t0 { text-decoration-color: var(--t0-line); }
a.rec.t1 { text-decoration-color: var(--t1-line); }
a.rec.t2 { text-decoration-color: var(--t2-line); }
a.rec.t3 { text-decoration-color: var(--t3-line); }
a.rec.t4 { text-decoration-color: var(--t4-line); text-decoration-style: dashed; }
a.rec.key { font-family: var(--font-mono); font-size: 0.82em; }
.rec.missing { color: var(--warn); font-family: var(--font-mono); font-size: 0.82em; }
.flash, tr.flash > td { background-color: var(--mark); transition: none; }

/* tables */
.tablewrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); }
table { border-collapse: collapse; }
table.md, table.rt { width: 100%; font: 13.5px/1.45 var(--font-ui); }
table.md { min-width: 640px; }
table.rt { min-width: 780px; }
table.md th, table.rt th {
  padding: 9px 12px; border-bottom: 1px solid var(--line-strong); background: var(--surface);
  color: var(--muted); font-size: 12px; font-weight: 600; letter-spacing: 0.04em;
  text-align: left; text-transform: uppercase; vertical-align: bottom;
}
table.md td, table.rt td { padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
table.md tbody tr:last-child td, table.rt tbody tr:last-child td { border-bottom: 0; }
table.md .r { text-align: right; }
table.md .c { text-align: center; }
table.rt td.name { min-width: 15em; max-width: 30em; }
table.rt td { transition: background-color 1.2s ease-out; }
.sm-col { color: var(--muted); font-size: 12.5px; }
th.num, td.num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
.sm { display: block; margin-top: 2px; color: var(--muted); font-size: 12.5px; line-height: 1.4; }

/* catalog engine */
.controls { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin: 0 0 14px; }
.controls input[type="search"], .controls select {
  min-width: 0; max-width: 100%; padding: 7px 10px; border: 1px solid var(--line-strong);
  border-radius: 4px; background: var(--bg); color: var(--fg); font: 14px/1.3 var(--font-ui);
}
.controls input[type="search"] { flex: 1 1 280px; }
.theme {
  padding: 7px 11px; border: 1px solid var(--line-strong); border-radius: 4px;
  background: var(--bg); color: var(--fg); font: 14px/1.3 var(--font-ui); cursor: pointer;
}
.theme:hover { background: var(--surface); }
.layerhead { margin: 6px 0; color: var(--muted); font-size: 11.5px; letter-spacing: 0.06em; text-transform: uppercase; }
.chips { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 6px; margin: 0 0 12px; }
.chip {
  display: flex; align-items: center; gap: 8px; min-height: 30px; padding: 5px 10px;
  border: 1px solid var(--line); border-radius: 4px; background: var(--surface); color: inherit;
  font: 12.5px/1.25 var(--font-ui); text-align: left; cursor: pointer;
}
.chip:hover { border-color: var(--line-strong); }
.chip.adj { border-style: dashed; }
.chip .lab { flex: 1 1 auto; min-width: 0; }
.chip .n { flex: none; color: var(--muted); font-variant-numeric: tabular-nums; }
.chip[aria-pressed="true"] { border-color: var(--accent); background: var(--accent); color: var(--on-accent); }
.chip[aria-pressed="true"] .n { color: inherit; }
.count { margin: 4px 0 10px; color: var(--muted); font-size: 13px; font-variant-numeric: tabular-nums; }
.stats { margin: 0 0 16px; }
.panels { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }
.panel { display: flex; flex-direction: column; min-width: 0; border: 1px solid var(--line); border-radius: 6px; background: var(--bg); }
.kpi { padding: 10px 12px 8px; border-bottom: 1px solid var(--line); }
.kpi .k { color: var(--muted); font-size: 12px; }
.kpi .v { font-size: 24px; font-weight: 650; line-height: 1.25; font-variant-numeric: tabular-nums; }
.kpi .s { color: var(--muted); font-size: 11.5px; }
.chart { padding: 8px 12px 6px; }
.chart h3 { margin: 0; font-size: 12.5px; font-weight: 600; }
.chart p { margin: 1px 0 4px; color: var(--muted); font-size: 11.5px; }
.chart svg { display: block; width: 100%; height: auto; }
.chart .band:hover { fill: var(--fg); fill-opacity: 0.05; }
.catalog table { width: 100%; min-width: 1040px; font-size: 13.5px; }
.catalog th, .catalog td { padding: 9px 11px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
.catalog thead th {
  background: var(--surface); color: var(--muted); cursor: pointer; white-space: nowrap;
  font-size: 12px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase;
}
.catalog thead th:hover { color: var(--fg); }
.catalog th .ar { font-size: 10px; }
.catalog thead th.num { text-align: right; }
.catalog tr.filters th { padding: 4px 6px; border-bottom-color: var(--line-strong); cursor: default; text-transform: none; letter-spacing: 0; font-weight: 400; }
.catalog tr.filters input {
  width: 100%; min-width: 58px; padding: 3px 6px; border: 1px solid var(--line); border-radius: 3px;
  background: var(--bg); color: var(--fg); font: 12px var(--font-ui);
}
.catalog tbody tr:not(.detail):hover > td { background: var(--surface); }
.catalog tbody td { transition: background-color 1.2s ease-out; }
.catalog tbody tr.hl > td, .catalog tbody tr.hl:hover > td { background: var(--mark); transition: none; }
.catalog td.name { min-width: 220px; max-width: 380px; }
.catalog td.rg { min-width: 220px; max-width: 320px; font-size: 13px; }
.catalog td.rg .gs { color: var(--muted); font-size: 11.5px; }
.catalog td.lnk { white-space: nowrap; font-size: 12.5px; }
.catalog td.lnk a { margin-right: 6px; }
.nm.more {
  display: inline; padding: 0; border: 0; background: none; color: var(--accent);
  font: 650 14px/1.35 var(--font-ui); text-align: left; cursor: pointer;
}
.nm.more:hover { text-decoration: underline; }
.nm.more::after {
  content: ""; display: inline-block; width: 0.42em; height: 0.42em; margin-left: 0.5em;
  border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor;
  transform: translateY(-0.2em) rotate(45deg); transition: transform 0.15s;
}
.nm.more[aria-expanded="true"]::after { transform: translateY(0.05em) rotate(-135deg); }
.no { color: var(--faint); }
.cat {
  display: inline-block; margin: 1px 3px 1px 0; padding: 1px 6px; border: 1px solid var(--line);
  border-radius: 3px; background: var(--surface); color: var(--muted); font-size: 11.5px; white-space: nowrap;
}
.cat.adj { border-style: dashed; }
.req { display: inline-block; margin: 0 4px 1px 0; color: var(--muted); font-size: 11.5px; white-space: nowrap; }
.bm { display: block; margin-top: 3px; font-size: 11.5px; }
.cav { border-bottom: 1px dotted currentColor; color: var(--warn); font-size: 11.5px; cursor: help; }
.ok { color: var(--ok); font-size: 12px; }
.bad { color: var(--warn); font-size: 12px; font-weight: 700; }
.arch { color: var(--warn); font-size: 11.5px; }
.agg { display: block; color: var(--muted); font-size: 11px; cursor: help; }
.empty { padding: 28px; color: var(--muted); text-align: center; }
.catalog tr.detail > td { padding: 0; background: var(--surface); }
.rd {
  position: sticky; left: 0; padding: 14px 16px 16px;
  width: min(80ch, calc(100vw - 2 * max(16px, env(safe-area-inset-left, 0px)) - 4px));
}
.rd dl { display: grid; grid-template-columns: 7.5em minmax(0, 1fr); gap: 7px 14px; margin: 0; font-size: 13.5px; line-height: 1.5; }
.rd dt { padding-top: 2px; color: var(--muted); font-size: 11.5px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; }
.rd dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.rd .dim { color: var(--muted); }
#tip {
  position: fixed; z-index: 50; pointer-events: none; opacity: 0;
  max-width: min(44ch, calc(100vw - 16px)); padding: 8px 11px;
  border: 1px solid var(--line-strong); border-radius: 6px; background: var(--bg); color: var(--fg);
  font: 12.5px/1.45 var(--font-ui); white-space: normal; text-align: left;
  box-shadow: 0 4px 16px var(--shadow); transition: opacity 0.1s;
}
#tip b { font-weight: 650; }
#tip ul { margin: 6px 0 0; padding-left: 1.1em; }
#tip li { margin: 2px 0; }
#tip .tl { display: block; margin-top: 6px; color: var(--muted); }
#tip .tier { font-size: 11px; }
th[data-k] { cursor: pointer; }
th[data-k]:focus-visible { outline-offset: -2px; }
.notes { max-width: 90ch; margin-top: 22px; color: var(--muted); font-size: 12.5px; line-height: 1.7; }

@media (max-width: 1100px) {
  .masthead { grid-template-columns: minmax(0, 1fr); grid-template-areas: "title" "id" "legend"; gap: 8px; }
  .legend { margin-top: 8px; }
  .legend { max-width: 46rem; }
}
@media (max-width: 600px) {
  .chapters .cur { display: none; }
  .hub { font-size: 24px; }
  .view-head h1 { font-size: 25px; }
  .prose { font-size: 16.5px; }
  .legend dl { grid-template-columns: max-content minmax(0, 1fr); gap: 2px 10px; }
  .legend .cnt { text-align: left; }
  .legend .mean { grid-column: 1 / -1; margin-bottom: 6px; }
  .rd dl { grid-template-columns: minmax(0, 1fr); gap: 2px; }
  .rd dd { margin-bottom: 8px; }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; scroll-behavior: auto !important; }
}
"""

THEME_BUTTON = (
    '<button class="icon-btn" id="theme" type="button" aria-label="Switch between light and dark" '
    'data-tip="Switch between light and dark"><svg viewBox="0 0 16 16" width="16" height="16" '
    'aria-hidden="true"><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" '
    'stroke-width="1.5"></circle><path d="M8 1.75a6.25 6.25 0 0 1 0 12.5z" fill="currentColor">'
    "</path></svg></button>")

HUB_CATALOG = r"""<section class="view catalog" data-view="catalog" aria-labelledby="catalog-title"__HIDDEN__>
<header class="view-head">
<p class="eyebrow">Catalog</p>
<h1 id="catalog-title">All __COUNT__ records</h1>
<p class="stand">Search, filter and sort every record. Select a name to see its summary, evidence, citation and where the review discusses it.</p>
</header>
<div class="controls">
__FILTERS__
__DOWNLOAD_BUTTON__
</div>
__TABLE__
<footer class="notes">
__NOTES__
    The tab-separated and JSON catalog files are in the source repository,
    <a href="__REPO__">github.com/thirtysix/awesome-single-cell-qc</a>.
</footer>
</section>
"""

HUB_JS = r"""
// ---------------------------------------------------------------------------
// Hub page: one view at a time, named by a plain #token so that a link can
// open any chapter, section or record. A view token shows that view; a record
// id opens the catalog on that record; any other id opens the view holding it.
// ---------------------------------------------------------------------------
const VIEWS = __VIEWS__;
const REVIEW_LINK = __REVIEW_LINK__;
const CITED_IN = __CITED_IN__;
const viewTitle = new Map(VIEWS);
const recordById = new Map(RECORDS.map(t => [t.id, t]));
const sideDesc = Object.fromEntries(VOCAB.sides);
const TOKEN = /^[A-Za-z0-9._~-]+$/;
const smooth = () => !matchMedia('(prefers-reduced-motion: reduce)').matches;
const openRecords = new Set();
const scrollAt = {};
let current = null;

function hubReviewHref(t) {
  return REVIEW_LINK[t.id] ? '#' + REVIEW_LINK[t.id][1] : '';
}
function hubNameButton(t) {
  return '<button class="nm more" type="button" data-id="' + esc(t.id) + '" aria-expanded="' +
    openRecords.has(t.id) + '">' + esc(t.name) + '</button>';
}
// [[id]], [[id#anchor]] and [[id|label]] in already-escaped text, named the way
// the chapters name them: tools by name, evidence and hypotheses by id.
const REF = /\[\[([^\[\]|#]+?)(?:#[^\[\]|]*)?(?:\|([^\[\]]*))?\]\]/g;
function hubRefs(html) {
  return html.replace(REF, (whole, id, label) => {
    const t = recordById.get(id.trim());
    if (!t) return whole;
    const key = !label && ['evidence', 'hypothesis'].includes(t.kind);
    const text = label ? label.trim() : key ? t.id : (t.name.replace(/\s*\([^()]*\)\s*$/, '') || t.name);
    const rank = t.tier_rank >= 0 ? Math.min(t.tier_rank, 4) : 4;
    const tipHtml = '<b>' + esc(t.name) + '</b> <span class="tier t' + rank + '">' + esc(t.tier) + '</span><br>' + esc(t.summary);
    return '<a href="#' + esc(t.id) + '" class="rec t' + rank + (key ? ' key' : '') + '" data-tip="' + esc(tipHtml) + '">' + (label ? text : esc(text)) + '</a>';
  });
}
const viewLabel = token => (/^ch\d/.test(token) ? token.slice(2, 4) + ' ' : '') + (viewTitle.get(token) || token);
const linkTo = (token, eid) => '<a href="#' + esc(eid) + '">' + esc(viewLabel(token)) + '</a>';
const bare = u => u.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '');

function hubDetailRow(t) {
  if (!openRecords.has(t.id)) return '';
  const rows = [];
  const add = (label, value) => { if (value) rows.push('<dt>' + label + '</dt><dd>' + value + '</dd>'); };
  const rank = t.tier_rank >= 0 ? Math.min(t.tier_rank, 4) : 4;
  add('Summary', prose(t.summary));
  add('Tier', '<span class="tier t' + rank + '">' + esc(t.tier) + '</span> ' + esc(tierDesc[t.tier] || ''));
  add('Side', '<b>' + esc(t.side) + '</b> <span class="dim">' + esc(sideDesc[t.side] || '') + '</span>');
  add('Recovers', prose(t.recovers));
  if (t.gain) add('Gain', prose(t.gain) + (t.gain_source ? ' <span class="dim">(' + esc(t.gain_source) + ')</span>' : ''));
  add('Requires', (t.requires || []).map(r => esc(r)).join(', '));
  add('Caveats', prose(t.caveats));
  const cite = [];
  const where = [t.publication_venue, t.year].filter(Boolean).join(', ');
  if (t.cite_title || t.publication_title)
    cite.push(esc(t.cite_title || t.publication_title) + (where ? ' <span class="dim">' + esc(where) + '</span>' : ''));
  const ids = [];
  if (t.doi) ids.push('<a href="https://doi.org/' + esc(t.doi) + '">doi:' + esc(t.doi) + '</a>');
  if (t.pmid) ids.push('<a href="https://pubmed.ncbi.nlm.nih.gov/' + esc(t.pmid) + '/">PMID ' + esc(t.pmid) + '</a>');
  if (!ids.length && t.publication_url)
    ids.push('<a href="' + esc(t.publication_url) + '">' + (t.publication_is_preprint ? 'preprint' : 'paper') + '</a>');
  if (t.citation_check === 'mismatch') ids.push('<span class="bad">the last citation check contradicted this record</span>');
  else if (t.verified) ids.push('<span class="ok">identifier fetched, title matched</span>');
  if (ids.length) cite.push(ids.join(' · '));
  add('Citation', cite.join('<br>'));
  const seen = new Set();
  const links = [t.site, t.repo_url, t.url].filter(u => u && !seen.has(bare(u)) && seen.add(bare(u)))
    .map(u => '<a href="' + esc(u) + '">' + esc(bare(u)) + '</a>');
  add('Links', links.join(' · '));
  add('Benchmarks', (t.benchmark_refs || []).map(b => '<a href="' + esc(b.url) + '">' + esc(b.name) + '</a>').join(' · '));
  const home = REVIEW_LINK[t.id];
  const others = (CITED_IN[t.id] || []).filter(([token]) => !home || token !== home[0]);
  let review = home ? 'Discussed in ' + linkTo(home[0], home[1]) : '';
  if (others.length)
    review += (review ? '; also cited in ' : 'Cited in ') + others.map(([tk, eid]) => linkTo(tk, eid)).join(', ');
  add('In the review', review);
  return '<tr class="detail"><td colspan="10"><div class="rd"><dl>' + rows.join('') + '</dl></div></td></tr>';
}

function showView(token) {
  if (token === current) return false;
  if (current !== null) scrollAt[current] = scrollY;
  document.querySelectorAll('[data-view]').forEach(v => { v.hidden = v.dataset.view !== token; });
  document.querySelectorAll('[data-nav]').forEach(a => {
    const on = a.dataset.nav === token;
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    a.parentElement.classList.toggle('on', on);
  });
  current = token;
  const menu = document.querySelector('.chapters');
  if (menu) {
    menu.classList.toggle('on', token !== 'catalog');
    menu.querySelector('.cur').textContent = token === 'catalog' ? '' : viewLabel(token);
    menu.open = false;
  }
  if (token === 'catalog' && statsOpen) renderStats(RECORDS.filter(matches));
  return true;
}

function clearFilters() {
  state.q = ''; state.cats.clear(); state.col = {};
  ['layer', 'kind', 'tier', 'side', 'requires'].forEach(k => { state[k] = ''; $(k).value = ''; });
  $('q').value = '';
  document.querySelectorAll('[data-f]').forEach(el => { el.value = ''; });
}

function flash(el) {
  el.classList.remove('flash');
  el.classList.add('flash');
  setTimeout(() => el.classList.remove('flash'), 1400);
}

function focusRecord(id) {
  showView('catalog');
  if (!RECORDS.filter(matches).some(t => t.id === id)) clearFilters();
  openRecords.add(id);
  render();
  $('rows').querySelectorAll('tr.hl').forEach(r => r.classList.remove('hl'));
  const row = [...$('rows').querySelectorAll('tr[data-id]')].find(r => r.dataset.id === id);
  if (!row) return;
  row.classList.add('hl');
  row.scrollIntoView({ block: 'start', behavior: smooth() ? 'smooth' : 'auto' });
  row.querySelector('button.more').focus({ preventScroll: true });
}

function go(token) {
  if (!token || !TOKEN.test(token)) token = 'catalog';
  if (viewTitle.has(token)) {
    const changed = showView(token);
    scrollTo(0, changed ? (scrollAt[token] || 0) : 0);
    return;
  }
  if (recordById.has(token)) { focusRecord(token); return; }
  const el = document.getElementById(token);
  const view = el && el.closest('[data-view]');
  if (view) {
    showView(view.dataset.view);
    el.scrollIntoView({ block: 'start' });
    if (el.matches('a.rec, tr')) flash(el);
    return;
  }
  // a section that has since been renamed still opens its chapter
  const owner = VIEWS.find(([v]) => token.startsWith(v + '-'));
  go(owner ? owner[0] : 'catalog');
}

document.addEventListener('click', e => {
  if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
  const a = e.target.closest('a[href^="#"]');
  if (!a) return;
  const token = a.getAttribute('href').slice(1);
  if (!TOKEN.test(token)) return;
  e.preventDefault();
  try { history.pushState(null, '', '#' + token); } catch (err) { /* no history here: the view still changes */ }
  go(token);
});
addEventListener('popstate', () => go(location.hash.slice(1)));

$('rows').addEventListener('click', e => {
  const b = e.target.closest('button.more');
  if (!b) return;
  const id = b.dataset.id;
  if (openRecords.has(id)) openRecords.delete(id); else openRecords.add(id);
  render();
  const again = [...$('rows').querySelectorAll('button.more')].find(x => x.dataset.id === id);
  if (again) again.focus({ preventScroll: true });
});

// Concept map: pointing at a node lights its edges and the nodes at their other ends.
document.querySelectorAll('.cmap-svg').forEach(svg => {
  const clear = () => { svg.classList.remove('hl'); svg.querySelectorAll('.on').forEach(x => x.classList.remove('on')); };
  const light = node => {
    clear();
    const key = node.dataset.c ? ['c', node.dataset.c] : ['q', node.dataset.q];
    const edges = [...svg.querySelectorAll('.e')].filter(e => e.dataset[key[0]] === key[1]);
    const ends = new Set(edges.flatMap(e => ['c:' + e.dataset.c, 'q:' + e.dataset.q]));
    edges.forEach(e => e.classList.add('on'));
    svg.querySelectorAll('.n').forEach(n => {
      if (n === node || ends.has(n.dataset.c ? 'c:' + n.dataset.c : 'q:' + n.dataset.q)) n.classList.add('on');
    });
    svg.classList.add('hl');
  };
  svg.querySelectorAll('.n').forEach(n => {
    n.addEventListener('mouseenter', () => light(n));
    n.addEventListener('focus', () => light(n));
    n.addEventListener('mouseleave', clear);
    n.addEventListener('blur', clear);
  });
});

// The chapters menu closes on a choice, a click elsewhere or Escape.
const chapterMenu = document.querySelector('.chapters');
if (chapterMenu) {
  chapterMenu.addEventListener('click', e => { if (e.target.closest('a')) chapterMenu.open = false; });
  document.addEventListener('click', e => { if (!chapterMenu.contains(e.target)) chapterMenu.open = false; });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') chapterMenu.open = false; });
}

render();
go(location.hash.slice(1));
"""


def _hub_masthead(catalog: dict, views: list[ReviewView]) -> str:
    records = catalog.get("records") or []
    by_tier = {k: 0 for k in TIERS}
    for t in records:
        by_tier[t["tier"]] = by_tier.get(t["tier"], 0) + 1
    by_layer = {k: 0 for k in LAYERS}
    for t in records:
        by_layer[t["layer"]] = by_layer.get(t["layer"], 0) + 1
    layers = ", ".join(f"{n} {k}" for k, n in by_layer.items())
    chapters = sum(1 for v in views if v.token != "overview")
    rows = "\n".join(
        f'<div class="row"><dt><span class="tier t{min(i, 4)}">{_esc(k)}</span></dt>'
        f'<dd class="cnt">{by_tier.get(k, 0)}</dd><dd class="mean">{_esc(desc)}</dd></div>'
        for i, (k, desc) in enumerate(TIERS.items()))
    return f"""<header class="masthead">
<div class="titlerow"><h1 class="hub">{TITLE}</h1>{THEME_BUTTON}</div>
<div class="id">
<p class="desc">{_esc(HUB_DESCRIPTION)}</p>
<p class="meta"><span>{plural(len(records), "record")} ({layers})</span><span>{plural(chapters, "review chapter")}</span><span>built {_esc(catalog["meta"]["generated"])}</span></p>
<p class="meta">Source, with the TSV and JSON catalog: <a href="{REPO_URL}">github.com/thirtysix/awesome-single-cell-qc</a></p>
</div>
<details class="legend">
<summary>How to read tiers</summary>
<dl>
{rows}
</dl>
<p class="legend-note">In the chapters, a record link is underlined in its tier colour; a dashed line marks a hypothesis.</p>
</details>
</header>"""


def _hub_rail(views: list[ReviewView], n_records: int) -> str:
    """The top bar: the catalog (the landing view), then a menu of the chapters."""
    items = []
    for v in views:
        overview = v.token == "overview"
        items.append(
            f'<li><a href="#{v.token}" data-nav="{v.token}" data-tip="{_attr(_esc(v.title))}">'
            f'<span class="num">{"" if overview else v.number}</span>'
            f'<span class="lbl">{_esc(v.short)}</span></a></li>')
    menu = ""
    if items:
        menu = ('<details class="chapters"><summary data-tip="The review: an overview, then a chapter '
                'on each QC stage and on the analysis steps QC feeds into.">Chapters '
                '<span class="cur"></span></summary>\n'
                '<ol class="menu">\n' + "\n".join(items) + "\n</ol>\n</details>\n")
    return ('<nav class="topbar" aria-label="Report">\n'
            '<a class="v" href="#catalog" data-nav="catalog" data-tip="Every record, with search, '
            'filters, sortable columns and summary panels.">Catalog'
            f'<span class="n">{n_records}</span></a>\n' + menu + "</nav>")


def _hub_view(v: ReviewView, hidden: bool) -> str:
    overview = v.token == "overview"
    eyebrow = "Overview" if overview else f"Chapter {v.number}"
    cited = plural(len(v.page.mentions), "record")
    stand = (f"{cited} cited in the text" if overview or not v.n_records
             else f"{plural(v.n_records, 'record')} reviewed here, {cited} cited in the text")
    toc = ""
    if v.page.toc:
        toc = ('<nav class="ch-toc" aria-label="In this chapter"><p>In this chapter</p><ol>'
               + "".join(f'<li class="h{level}"><a href="#{eid}">{_esc(text)}</a></li>'
                         for level, text, eid in v.page.toc) + "</ol></nav>\n")
    return (f'<section class="view" data-view="{v.token}" aria-labelledby="{v.token}-title"'
            f'{" hidden" if hidden else ""}>\n<header class="view-head"><p class="eyebrow">'
            f'{eyebrow}</p><h1 id="{v.token}-title">{_esc(v.title)}</h1>'
            f'<p class="stand">{stand}</p></header>\n{toc}<div class="prose">\n{v.html}\n</div>\n'
            "</section>")


DOWNLOAD_BUTTON = ('<button class="theme" id="dl" type="button" data-tip="Download the rows '
                   'currently shown, in the current sort order, as a tab-separated file with the '
                   'columns of data/catalog.tsv.">'
                   'Download</button>')


def render_site(catalog: dict, review_dir: Path = REVIEW_DIR) -> str:
    """docs/index.html: the hub as a whole document, with downloads."""
    return render_hub(catalog, review_dir, document=True)


def render_hub(catalog: dict, review_dir: Path = REVIEW_DIR, document: bool = False) -> str:
    """dist/hub.html: the review chapters and the catalog explorer in one file.

    By default page content only, for a host that supplies the document
    skeleton; see the comment above PUBMED for the rules it keeps. With
    `document`, a whole page for a static host (GitHub Pages): doctype, charset
    and viewport, and a button that downloads the rows shown.
    """
    records = catalog.get("records") or []
    views = hub_views(catalog, review_dir)
    review_link, cited = review_index(views, records)
    tokens = [[v.token, v.short] for v in views]
    tokens.append(["catalog", "Catalog"])
    # The shared catalog pieces and their vocabulary go in first; the record
    # data, chapter text and view index go in last, so a placeholder-like
    # string inside a record can never be substituted.
    catalog_part = _fill_catalog(
        HUB_CATALOG.replace("__HIDDEN__", "")
        .replace("__REPO__", REPO_URL)
        .replace("__DOWNLOAD_BUTTON__\n", DOWNLOAD_BUTTON + "\n" if document else "")
        + "<script>\n__CATALOG_JS__\n__HUB_JS__"
        + ("\n__DOWNLOAD_JS__" if document else "") + "</script>",
        catalog, standalone=True)
    hub_js = (HUB_JS.replace("__VIEWS__", _js_json(tokens))
              .replace("__REVIEW_LINK__", _js_json(review_link))
              .replace("__CITED_IN__", _js_json(cited)))
    script_at = catalog_part.index("<script>")
    head = [f"<title>{TITLE}</title>",
            '<meta name="claude:viewport-fit-sides" content="cover">',
            "<style>", hub_theme_css() + HUB_CSS.strip("\n"), "</style>"]
    if document:
        head = ['<!doctype html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
                f"<title>{TITLE}</title>",
                f'<meta name="description" content="{_attr(HUB_DESCRIPTION)}">',
                "<style>", hub_theme_css() + HUB_CSS.strip("\n"), "</style>",
                "</head>", "<body>"]
    parts = [
        *head,
        '<div class="frame">',
        _hub_masthead(catalog, views),
        '<div class="layout">',
        _hub_rail(views, len(records)),
        '<main class="views-main" id="main">',
        *[_hub_view(v, hidden=True) for v in views],
        catalog_part[:script_at].rstrip("\n"),
        "</main>",
        "</div>",
        "</div>",
        '<div id="tip" role="tooltip"></div>',
        f"<script>\n{catalog_js(catalog)}</script>",
        catalog_part[script_at:].replace("__HUB_JS__", hub_js.lstrip("\n")),
    ]
    if document:
        parts += ["</body>", "</html>"]
    return "\n".join(parts) + "\n"


def write_standalone(catalog: dict, path: Path = STANDALONE,
                     review_dir: Path = REVIEW_DIR) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_hub(catalog, review_dir))
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--catalog", type=Path, default=CATALOG)
    ap.add_argument("--review-dir", type=Path,
                    default=Path(os.environ.get("REVIEW_DIR") or REVIEW_DIR),
                    help="chapters whose records:start/end region is filled, and "
                         "which --standalone puts on the page "
                         "(default: $REVIEW_DIR or docs/review)")
    ap.add_argument("--standalone", action="store_true",
                    help="write only dist/hub.html: the review chapters and the "
                         "catalog, inlined")
    ap.add_argument("--out", type=Path, default=STANDALONE,
                    help="where --standalone writes (default: dist/hub.html)")
    args = ap.parse_args(argv)

    if not args.catalog.exists():
        print(f"error: {args.catalog} not found; run `make build` first", file=sys.stderr)
        return 2
    catalog = json.loads(args.catalog.read_text())
    n = catalog["meta"]["count"]

    if args.standalone:
        path = write_standalone(catalog, args.out, args.review_dir)
        pages = len(hub_views(catalog, args.review_dir))
        print(f"{path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}  "
              f"{path.stat().st_size / 1024:.1f} KB ({n} records, "
              f"{plural(pages, 'review page')}, self-contained)")
        return 0

    README.write_text(render_readme(catalog) + "\n")
    RECORDS_MD.write_text(render_records_md(catalog) + "\n")
    reviewed = render_review(catalog, args.review_dir)
    index = write_site(catalog, review_dir=args.review_dir)
    print(f"README.md          {README.stat().st_size / 1024:.1f} KB")
    print(f"docs/records.md    {RECORDS_MD.stat().st_size / 1024:.1f} KB")
    print(f"docs/index.html    {index.stat().st_size / 1024:.1f} KB ({n} records)")
    for path, outcome in reviewed:
        print(f"review {path.name}: {outcome}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
