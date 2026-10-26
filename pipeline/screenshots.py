#!/usr/bin/env python3
"""README screenshots of the site, from the built docs/index.html.

    docs/screenshots/catalog.webp   the landing view: chips, summary panels, table
    docs/screenshots/record.webp    a column filter, a record's details, a header tooltip
    docs/screenshots/chapter.webp   a review chapter

    python pipeline/screenshots.py      (or `make screenshots`, after `make curate`)

Maintainer tooling: needs Playwright with Chromium (`pip install playwright`,
`playwright install chromium`) and Pillow, neither of which the pipeline needs.
The page is one self-contained file, so it is opened straight from disk.
Native scale at a 1600px viewport: GitHub shows README images at about 880px,
so this is already sharper than retina there, at a fraction of the size.
"""
from __future__ import annotations

import io
import json
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

from config import DATA, DOCS

OUT = DOCS / "screenshots"
VIEWPORT = {"width": 1600, "height": 1000}


def save(png: bytes, name: str) -> None:
    path = OUT / f"{name}.webp"
    Image.open(io.BytesIO(png)).convert("RGB").save(path, "WEBP", quality=82, method=6)
    print(f"{path.relative_to(DOCS.parent)}  {path.stat().st_size / 1024:.0f} KB")


def main() -> int:
    n = json.loads((DATA / "catalog.json").read_text())["meta"]["count"]
    url = (DOCS / "index.html").resolve().as_uri()
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport=VIEWPORT, color_scheme="light")
        pg = ctx.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        pg.goto(url)
        pg.wait_for_selector("#rows tr[data-id]")
        # the build we meant to shoot: the page's own record count
        heading = pg.inner_text("#catalog-title")
        assert heading == f"All {n} records", f"stale build? page says {heading!r}, catalog {n}"
        pg.add_style_tag(content="*{transition:none!important;animation:none!important}")
        save(pg.screenshot(), "catalog")

        pg.click("#stats-toggle")
        pg.fill('input[data-f="name"]', "demuxmix")
        pg.wait_for_timeout(400)                 # column filters are debounced
        pg.locator('#rows button.more[data-id="demuxmix"]').click()
        pg.wait_for_selector('#rows tr.detail')
        top = pg.evaluate("document.getElementById('count').getBoundingClientRect().top + scrollY")
        pg.evaluate(f"window.scrollTo(0, {top} - 70)")
        pg.wait_for_timeout(300)                 # let the scroll settle before the tooltip opens
        pg.locator('th[data-k="tier_rank"]').hover()
        pg.wait_for_timeout(200)
        assert pg.evaluate("getComputedStyle(document.getElementById('tip')).opacity") == "1", "no tooltip"
        save(pg.screenshot(), "record")

        pg.goto(url + "#ch01")
        pg.wait_for_selector('[data-view="ch01"]:not([hidden])')
        pg.mouse.move(5, 5)
        save(pg.screenshot(), "chapter")
        browser.close()
    if errors:
        print("page errors:", *errors, sep="\n  ", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
