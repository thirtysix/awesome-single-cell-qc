"""config.is_preprint: which DOIs are preprint deposits rather than published papers.

Ported from the regulatory-genomics catalog, where treating the whole 10.1101/
prefix as bioRxiv labelled peer-reviewed Genome Research papers as preprints.
"""
import pytest

from config import PREPRINT_PREFIXES, is_preprint


@pytest.mark.parametrize("doi", [
    "10.1101/2024.12.25.630221",     # dated bioRxiv
    "10.1101/2023.03.17.533005",     # dreamlet's bioRxiv preprint
    "10.1101/867309",                # legacy all-digit bioRxiv
    "10.1101/2020.11.09.373613v2",   # with a version suffix
    "10.21203/RS.2.20856/V2",        # Research Square
    "10.48550/arXiv.2301.00001",     # arXiv
])
def test_deposits_are_preprints(doi):
    assert is_preprint(doi)


@pytest.mark.parametrize("doi", [
    "10.1101/gr.137323.112",         # Genome Research
    "10.1101/gad.123456",            # Genes & Development
    "10.1101/cshperspect.a018713",   # CSH Perspectives
    "10.1186/s13059-019-1662-y",     # Genome Biology (EmptyDrops)
    "10.12688/f1000research.73600.2",  # F1000Research is post-publication peer review
])
def test_journal_articles_are_not_preprints(doi):
    """10.1101 is Cold Spring Harbor Laboratory Press, not a preprint prefix."""
    assert not is_preprint(doi)


@pytest.mark.parametrize("form", ["doi:{}", "https://doi.org/{}", "{}"])
def test_identifier_spellings_are_accepted(form):
    assert is_preprint(form.format("10.1101/2024.12.25.630221"))
    assert not is_preprint(form.format("10.1101/gr.137323.112"))


def test_every_listed_prefix_is_a_preprint():
    for prefix in PREPRINT_PREFIXES:
        assert is_preprint(prefix + "something"), prefix


def test_empty_and_pmid_identifiers_are_not_preprints():
    assert not is_preprint("")
    assert not is_preprint(None)
    assert not is_preprint("pmid:30902100")
