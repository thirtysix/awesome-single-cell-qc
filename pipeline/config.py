"""Shared configuration: paths, the record vocabulary, and API politeness.

The vocabulary (categories, layers, kinds, sides, tiers, requires, gain
sources) is NOT defined here. It is read from curation/schema.yaml, which is
the single source of truth: build.py validates records against it, render.py
draws its filters from it, and the tests fail on any value it does not list.
Changing the taxonomy means editing that one file.
"""
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = DATA / "cache"
CURATION = ROOT / "curation"
RECORDS_DIR = CURATION / "records"
BENCHMARKS = CURATION / "benchmarks.yaml"
EXPECTED = CURATION / "expected.yaml"
SCHEMA_PATH = CURATION / "schema.yaml"
DOCS = ROOT / "docs"
REVIEW_DIR = DOCS / "review"
DIST = ROOT / "dist"

OPENALEX_API = "https://api.openalex.org/works"
GITHUB_API = "https://api.github.com"
CROSSREF_API = "https://api.crossref.org/works/"
DATACITE_API = "https://api.datacite.org/dois/"
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"

# Network stages never run more than this many requests at once. The APIs here
# are shared infrastructure.
MAX_WORKERS = 4

# ---------------------------------------------------------------------------
# Record vocabulary, from curation/schema.yaml
# ---------------------------------------------------------------------------


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return yaml.safe_load(path.read_text()) or {}


SCHEMA = load_schema()
REQUIRED = list(SCHEMA.get("required") or [])
FIELDS = dict(SCHEMA.get("fields") or {})
LAYERS = dict(SCHEMA.get("layers") or {})
KINDS = dict(SCHEMA.get("kinds") or {})
SIDES = dict(SCHEMA.get("sides") or {})
TIERS = dict(SCHEMA.get("tiers") or {})
GAIN_SOURCES = dict(SCHEMA.get("gain_sources") or {})
REQUIRES = dict(SCHEMA.get("requires") or {})
# key -> {layer, title, desc}, in schema order. The order matters: it is the
# order of the README's sections and of the site's category chips.
CATEGORIES = dict(SCHEMA.get("categories") or {})
CATEGORY_KEYS = list(CATEGORIES)
CATEGORY_LABEL = {k: v.get("title", k) for k, v in CATEGORIES.items()}
CATEGORY_DESC = {k: v.get("desc", "") for k, v in CATEGORIES.items()}
CATEGORY_LAYER = {k: v.get("layer", "") for k, v in CATEGORIES.items()}


def enum_from_field(field: str) -> list[str]:
    """Allowed values written inline in a field description as `A | B | C`.

    `language` is the one field the schema enumerates this way rather than as
    its own block. Reading it from the description keeps the schema the only
    place the list lives.
    """
    desc = str(FIELDS.get(field) or "")
    if " | " not in desc:
        return []
    return [v.strip() for v in desc.split("|") if v.strip()]


LANGUAGES = enum_from_field("language")

# ---------------------------------------------------------------------------
# Preprint detection.
#
# `10.1101/` is NOT a preprint prefix. It belongs to Cold Spring Harbor
# Laboratory Press, which publishes bioRxiv *and* Genome Research, Genes &
# Development, RNA and the Perspectives series. Treating the whole prefix as
# preprint labelled peer-reviewed papers as preprints in the regulatory-genomics
# catalog this pipeline is forked from, RegulomeDB's Genome Research paper among
# them at 2,878 citations.
#
# Identify bioRxiv/medRxiv by the shape of the suffix instead of by excluding a
# list of journal abbreviations, because that list is not one we can be sure of
# completing: `10.1101/2024.12.25.630221` (dated) and `10.1101/867309` (legacy
# all-digit) are deposits, `10.1101/gr.137323.112` is a journal article.
PREPRINT_PREFIXES = ("10.21203/", "10.31234/", "10.20944/", "10.48550/")
_BIORXIV_SUFFIX = re.compile(r"^(?:\d{4}\.\d{2}\.\d{2}\.\d+|\d{6,})(?:v\d+)?$", re.I)


def is_preprint(ident: str) -> bool:
    """Is this identifier a preprint deposit rather than a published paper?"""
    doi = (ident or "").removeprefix("doi:").removeprefix("https://doi.org/").lower()
    if doi.startswith(PREPRINT_PREFIXES):
        return True
    if doi.startswith("10.1101/"):
        return bool(_BIORXIV_SUFFIX.match(doi[len("10.1101/"):]))
    return False

# ---------------------------------------------------------------------------
# Contact address for the API "polite pools"
# ---------------------------------------------------------------------------
# OpenAlex and Crossref give faster, more reliable service to clients that
# identify themselves, and ask for a contact address to do it. It is not a
# credential, but it is a personal detail, so it is configured rather than
# hard-coded: set CONTACT_EMAIL in the environment or in a local .env file.
#
# Unset is fine. Every caller omits the mailto parameter entirely rather than
# sending a placeholder, since a fake address in the polite pool is worse than
# no address at all.


def _load_dotenv() -> None:
    """Read a local .env if present. Deliberately no python-dotenv dependency."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv()
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "").strip()

# OpenAlex meters free use as a daily credit budget, not a per-second rate, and
# a key multiplies the allowance tenfold: $0.10/day anonymous against $1/day
# with a free key, at $0.0001 per request (1,000 vs 10,000 requests).
#
# The `mailto` polite pool does NOT help here and is a separate thing: a request
# with and without one gets byte-identical rate headers. Crossref still honours
# mailto, which is why CONTACT_EMAIL stays useful and separate.
OPENALEX_API_KEY = os.environ.get("OPENALEX_API_KEY", "").strip()
# NCBI E-utilities allow 3 requests/s anonymously and 10/s with a key.
NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "").strip()


def user_agent(tool: str = "awesome-single-cell-qc/0.1") -> str:
    """User-Agent string, with a contact address only if one is configured."""
    return f"{tool} (mailto:{CONTACT_EMAIL})" if CONTACT_EMAIL else tool


def polite_params(params: dict | None = None) -> dict:
    """Add the `mailto` courtesy address when configured, and nothing when not.

    Safe to send anywhere. Deliberately does NOT carry the OpenAlex key: this is
    used for Crossref too, and a credential belongs only in requests to the
    service that issued it.
    """
    out = dict(params or {})
    if CONTACT_EMAIL:
        out["mailto"] = CONTACT_EMAIL
    return out


def openalex_params(params: dict | None = None) -> dict:
    """Params for api.openalex.org only, including the key when one is set."""
    out = polite_params(params)
    if OPENALEX_API_KEY:
        out["api_key"] = OPENALEX_API_KEY
    return out


def openalex_tier() -> str:
    """One line describing the allowance this run has, for the stage banner."""
    return ("authenticated ($1/day, ~10,000 requests)" if OPENALEX_API_KEY
            else "anonymous ($0.10/day, ~1,000 requests) - set OPENALEX_API_KEY for 10x")


# ---------------------------------------------------------------------------
# Repository hosts
# ---------------------------------------------------------------------------
CODE_HOSTS = {
    "github.com": "github",
    "gitlab.com": "gitlab",
    "bitbucket.org": "bitbucket",
    "sourceforge.net": "sourceforge",
    "codeberg.org": "codeberg",
    "r-forge.r-project.org": "r-forge",
    "git.bioconductor.org": "bioconductor",
}
