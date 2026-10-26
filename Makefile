PY ?= python3
PORT ?= 8510
WORKERS ?= 3
PIPELINE := $(PY) pipeline

# Inputs. Override to build from somewhere else, e.g.
#   make curate RECORDS=tests/fixtures/records_seed.yaml BENCHMARKS=tests/fixtures/benchmarks_seed.yaml
# or use the FIXTURES=1 shortcut below. REVIEW is where render fills the
# records:start/end regions and where check resolves [[id]] links.
RECORDS ?= curation/records
BENCHMARKS ?= curation/benchmarks.yaml
REVIEW ?= docs/review

# `make curate FIXTURES=1` (or check/page/build-strict) builds from the test
# fixtures and fills the fixture review chapter, never touching curation/records
# or docs/review. The generated README, site and catalog are overwritten, so
# run a plain `make curate` afterwards to put the real records back.
ifdef FIXTURES
RECORDS := tests/fixtures/records_seed.yaml
BENCHMARKS := tests/fixtures/benchmarks_seed.yaml
REVIEW := tests/fixtures/review
endif

INPUTS := --records $(RECORDS) --benchmarks $(BENCHMARKS)

.PHONY: all test build build-strict render curate verify enrich check page serve \
        scview-import scview-proposal screenshots clean

## refresh the caches (network), then rebuild and check
all: verify enrich curate check

## unit tests: offline, no API keys
test:
	$(PY) -m pytest tests/ -q

## validate the records and write data/catalog.json + .tsv (offline)
build:
	$(PIPELINE)/build.py $(INPUTS)

## README.md, docs/records.md, docs/index.html (the site) and the review-chapter tables
render:
	$(PIPELINE)/render.py --review-dir $(REVIEW)

## rebuild everything generated from the records (offline)
curate: build render

## as build, but refuse unverified records (unless tier: hypothesis) and any
## mismatch in data/cache/verify.json
build-strict:
	$(PIPELINE)/build.py $(INPUTS) --strict

## check every doi/pmid against Crossref/PubMed (network, cached, at most 4 workers)
verify:
	$(PIPELINE)/verify_citations.py $(INPUTS) --workers $(WORKERS)

## citation counts (OpenAlex), repository activity (GitHub), publication metadata
enrich:
	$(PIPELINE)/enrich.py $(INPUTS)
	$(PIPELINE)/fill_metadata.py $(INPUTS)

## catalog sanity, [[id]] links in the review chapters, the denylist
check:
	$(PIPELINE)/check.py --review-dir $(REVIEW)

## dist/hub.html: the review chapters and the catalog in one self-contained page
page:
	$(PIPELINE)/render.py --standalone --review-dir $(REVIEW)

## preview the site at http://127.0.0.1:$(PORT)/ (loopback only)
serve:
	$(PY) -m http.server $(PORT) --bind 127.0.0.1 --directory docs

## docs/screenshots/*.webp for the README, from docs/index.html (needs playwright + chromium, Pillow)
screenshots:
	$(PIPELINE)/screenshots.py

# Maintainer tooling: needs a local scView checkout's research files and the
# untracked exchange/scview-map.yaml, neither of which is in a repository.
## exchange/scview-import.tsv: scView's QC rows against the hub (SCVIEW_CATALOG=... to move)
scview-import:
	$(PIPELINE)/scview_import.py

## exchange/scview-proposal-<date>.md: hub evidence and corrections for scView; never writes into scView
scview-proposal: scview-import
	$(PIPELINE)/scview_export.py

clean:
	rm -f data/catalog.json data/catalog.tsv docs/index.html docs/records.md dist/hub.html
