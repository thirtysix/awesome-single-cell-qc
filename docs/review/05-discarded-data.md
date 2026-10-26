# 05. Signal in discarded barcodes: doublets, lost cells and empty droplets

Standard QC throws away three kinds of barcode: doublets, damaged or low-RNA cells, and empty droplets, which include
hashtag negatives. Each of them carries information. Four things are shown in published work:

1. Some doublets are physically interacting cells ([PMID 31237234](https://pubmed.ncbi.nlm.nih.gov/31237234/)).
   Doublet-based tools can recover contact networks from routine data
   ([PMID 35536255](https://pubmed.ncbi.nlm.nih.gov/35536255/), [PMID 37638864](https://pubmed.ncbi.nlm.nih.gov/37638864/)).
2. The number of cells recovered per hashed condition tracks drug toxicity
   ([PMID 31806696](https://pubmed.ncbi.nlm.nih.gov/31806696/)).
3. Empty droplets measure the ambient background well enough to clean protein data
   ([PMID 35440536](https://pubmed.ncbi.nlm.nih.gov/35440536/)). In one pool, the ambient hashtag profile pointed to the
   most degraded sample ([PMID 31266958](https://pubmed.ncbi.nlm.nih.gov/31266958/)).
4. Common QC filters remove viable cells, including drug-resistant ones
   ([PMID 40205439](https://pubmed.ncbi.nlm.nih.gov/40205439/)).

What has not been shown is whether these signals work as per-condition readouts in high-multiplex drug
screens. We found no study that tests any of these against an orthogonal assay in that setting. In a screen with many
conditions and few cells each, the barcodes that QC removes are not a fixed tax. How many there are, and of what kind, can
differ by drug. That makes them a readout and a bias at the same time.

## Doublets as interactions

**Sorted pairs.** [PIC-seq](../records.md#pic-seq) sorts physically interacting cells and models each pair's transcriptome as a mixture of two
singlet profiles. It found regulatory T cells to be the main T cell subtype interacting with dendritic cells in mouse lymph
nodes ([PMID 32152598](https://pubmed.ncbi.nlm.nih.gov/32152598/)). Another group applied the PIC-seq model to unsorted
CITE-seq from 11 human kidney allograft biopsies (31,203 high-quality libraries). Three of six doublet clusters were called interacting
complexes. Two of those occurred at 4.7 and 9.5 times the frequency expected for artefactual doublets, while two other
clusters matched the expectation and were treated as artefacts
([PMID 37638864](https://pubmed.ncbi.nlm.nih.gov/37638864/)). This is the clearest published use of an expected
random-doublet rate as the test.

**Mining routine data.** [Neighbor-seq](../records.md#neighbor-seq) trains a random forest on artificial multiplets, assigns every barcode a
composition, and compares each cell-type pair's enrichment with re-simulated multiplets (100 by default). It recovered the microanatomy of
small intestinal epithelium, terminal respiratory tract and splenic white pulp, and tumour topologies that agreed with spatial data
([PMID 35536255](https://pubmed.ncbi.nlm.nih.gov/35536255/)). [CIcADA](../records.md#cicada) calls doublets from multi-label cell-type scores.
It keeps only clusters made entirely of observed doublets, then contrasts them with synthetic doublets of the same pair. In
tumour datasets these doublets up-regulated immune-response genes
([PMID 37745004](https://pubmed.ncbi.nlm.nih.gov/37745004/)). [ULMnet](../records.md#ulmnet) reported the only head-to-head comparison, on
FACS-sorted dendritic cell to T cell doublets with known partners. Sensitivity in vitro was 56% for ULMnet, 52.1% for
Neighbor-seq and 21.7% for CIcADA. In vivo it was 39%, 29.2% and 15.1%. Precision was about 99% for ULMnet and
Neighbor-seq ([PMID 41583424](https://pubmed.ncbi.nlm.nih.gov/41583424/)). The ULMnet authors ran this comparison
themselves.

**Designs that keep pairs on purpose.** ProximID, paired-cell sequencing and ClumpSeq sequence attached pairs or small
clumps, and use one partner's identity or zonation to map interactions or place the partner in tissue space ([PMID 29786092](https://pubmed.ncbi.nlm.nih.gov/29786092/),
[PMID 30222169](https://pubmed.ncbi.nlm.nih.gov/30222169/), [PMID 34031373](https://pubmed.ncbi.nlm.nih.gov/34031373/);
[Partial-dissociation sequencing](../records.md#partial-dissociation-seq)).

**Evidence that some doublets are biology.** T cell to monocyte complexes can be isolated from human blood. They show
polarised LFA1/ICAM1, and their frequency changes with infection and immunisation
([PMID 31237234](https://pubmed.ncbi.nlm.nih.gov/31237234/); [t-cell-monocyte-complexes](../records.md#t-cell-monocyte-complexes)). Such complexes also sit inside
the live-singlet gate, and one published "novel" mixed T and B population was likely made of them
([PMID 32400942](https://pubmed.ncbi.nlm.nih.gov/32400942/)). A 2026 review names the main obstacle: there are no definitive
markers that separate biological doublets from artefacts ([PMID 42601345](https://pubmed.ncbi.nlm.nih.gov/42601345/)). In
ovarian cancer, doublet-derived interaction networks were associated with response to therapy in cohorts of 7 and 13
patients ([PMID 40280979](https://pubmed.ncbi.nlm.nih.gov/40280979/), [PMID 42511520](https://pubmed.ncbi.nlm.nih.gov/42511520/)).
These are associations in small cohorts.

**The random-doublet baseline.** Random doublets follow Poisson loading. Their rate can be derived from mixing experiments
even when cell types are mixed unequally ([PMID 30202659](https://pubmed.ncbi.nlm.nih.gov/30202659/)). Hashing detects only
cross-sample doublets, so it gives a lower bound. Even so, the 10x heuristic consistently fell below hashing-based rates,
sometimes by more than twofold: 37% observed against 17% predicted in one mouse kidney dataset
([PMID 41166377](https://pubmed.ncbi.nlm.nih.gov/41166377/)). If the expected rate is set too low, every abundant pair
looks enriched. Neighbor-seq's null re-draws the observed cells and does not model loading
([PMID 35536255](https://pubmed.ncbi.nlm.nih.gov/35536255/)).

**Decomposing instead of discarding.** [DoubletDecon](../records.md#doubletdecon) returns putative doublet clusters that have unique gene expression
to the singlets. On mouse bone marrow its specificity rose from 80.7% to 95.0% with this rescue step
([PMID 31693907](https://pubmed.ncbi.nlm.nih.gov/31693907/)). In an independent benchmark, however, it did not beat a
library-size baseline, failed on four datasets and over-called doublets
([PMID 33338399](https://pubmed.ncbi.nlm.nih.gov/33338399/)). DeepDoublet splits hepatocyte to endothelial doublets into
their two transcriptomes ([PMID 39695909](https://pubmed.ncbi.nlm.nih.gov/39695909/)). RCTD doublet mode fits one or two
reference types per spatial pixel. On simulated doublets it called 81.1% correctly
([PMID 33603203](https://pubmed.ncbi.nlm.nih.gov/33603203/)). Nobody has reported using it on droplet doublets
([rctd-doublet-mode-droplets](../records.md#rctd-doublet-mode-droplets)).

## Lost and damaged cells as a drug-response readout

**Counts.** In [sci-Plex](../records.md#sci-plex), the number of cells recovered at each concentration gave a viability score that agreed with
gold-standard measurements. 52 of 188 compounds (27%) cut viability by half or more at the top dose
([PMID 31806696](https://pubmed.ncbi.nlm.nih.gov/31806696/); [Cell recovery per condition as a viability readout](../records.md#cell-recovery-viability)). Tahoe-100M reports quantifying
proliferation and cytotoxicity across 50 cell lines and 1,100 drug-dose conditions
([PMID 42753697](https://pubmed.ncbi.nlm.nih.gov/42753697/); [Tahoe-100M](../records.md#tahoe-100m)).

**Survivors can look unchanged.** [MIX-Seq](../records.md#mix-seq) predicted long-term viability from transcriptional responses (one model
across drugs, R2 0.50 at 24 h). The BCL-2 inhibitor navitoclax and the MCL1 inhibitor AZD5591 were the exceptions. Both
had strong selective viability effects but no robust transcriptional signature
([PMID 32855387](https://pubmed.ncbi.nlm.nih.gov/32855387/); [survivor-bias](../records.md#survivor-bias)). For drugs like these, the effect lives in
the cells that are gone. Drugs also change how much RNA a cell holds. Measured against spike-in molecules, paclitaxel or
celecoxib alone generally repressed transcription per cell, while the combination amplified it
([PMID 34159316](https://pubmed.ncbi.nlm.nih.gov/34159316/)). A count floor will therefore remove cells unevenly across
treatments. This is an inference; the study did not test filtering.

**Mitochondrial filters.** Across 9 tumour datasets (441,445 cells, 134 patients), malignant cells had higher mitochondrial
fractions without more dissociation stress. In 10 to 50% of tumour samples, cells above 15% mitochondrial reads were twice
as common among malignant cells as in the microenvironment. In lineage-traced ovarian cancer clones, those resistant to
olaparib or carboplatin had higher mitochondrial fractions than sensitive ones, rising further after treatment
([PMID 40205439](https://pubmed.ncbi.nlm.nih.gov/40205439/); [mito-filter-resistant-cells](../records.md#mito-filter-resistant-cells)). Adaptive thresholds are
covered in [miQC](../records.md#miqc), [ddqc](../records.md#ddqc) and [DropletQC](../records.md#dropletqc).

**Dead cells as a positive readout.** Pooled CRISPR screens already sequence dead cells to turn negative selection into
positive selection ([PMID 37166646](https://pubmed.ncbi.nlm.nih.gov/37166646/),
[PMID 37699398](https://pubmed.ncbi.nlm.nih.gov/37699398/)). MIX-Seq added floating cells back to the adherent fraction.

**Composition.** In a hashed pool, each condition's share of singlets is itself a composition, just like cell-type
proportions. [scCODA](../records.md#sccoda) models counts against a reference category (mean MCC 0.64 in its own simulations,
[PMID 34824236](https://pubmed.ncbi.nlm.nih.gov/34824236/)). [propeller (speckle) and Scanpro](../records.md#propeller) needs biological replicates
([PMID 36005887](https://pubmed.ncbi.nlm.nih.gov/36005887/)). Its Python port Scanpro bootstraps pseudo-replicates, which
by its authors' own account cannot reproduce biological variance
([PMID 38971877](https://pubmed.ncbi.nlm.nih.gov/38971877/)). [sccomp](../records.md#sccomp) models mean-variability association and excludes
outliers ([PMID 37549298](https://pubmed.ncbi.nlm.nih.gov/37549298/)). A best-practice review notes that composition
methods lack an independent benchmark [heumos-2023](../records.md#heumos-2023). All of them test
relative shares. A drug that kills every cell line equally leaves line shares unchanged, so absolute loss needs a
denominator: vehicle wells, or spike-in reference cells. Cross-species reference cells have been used to measure per-sample
contamination in drug-treated islets ([PMID 32375897](https://pubmed.ncbi.nlm.nih.gov/32375897/);
[Spike-in reference cells](../records.md#spike-in-reference-cells)). Their use as a count denominator is untested.

**Models that include loss.** Waddington-OT estimates growth and death rates with unbalanced transport, using priors from
proliferation and apoptosis signatures ([PMID 30712874](https://pubmed.ncbi.nlm.nih.gov/30712874/)). moscot accepts growth and
death rates as priors ([PMID 39843746](https://pubmed.ncbi.nlm.nih.gov/39843746/)). CellOT maps control cells onto treated cells
([PMID 37770709](https://pubmed.ncbi.nlm.nih.gov/37770709/)). Carrying a death term into drug-response models is proposed
here, not published ([unbalanced-ot-cell-loss](../records.md#unbalanced-ot-cell-loss)).

## Empty droplets and hashtag negatives

Empty droplets are already used as data. [EmptyDrops](../records.md#emptydrops) tests barcodes against the ambient profile. In [dsb](../records.md#dsb), protein
counts in empty droplets correlated with those of unstained spike-in cells, so they could serve as the background
([PMID 35440536](https://pubmed.ncbi.nlm.nih.gov/35440536/)). [demuxEM](../records.md#demuxem) estimates background hashtags from empty
droplets. In its brain-nuclei pool, one donor contributed disproportionately to that background. That donor had the lowest
RNA integrity number and the longest post-mortem interval of the cohort
([PMID 31266958](https://pubmed.ncbi.nlm.nih.gov/31266958/)). [DecontPro](../records.md#decontpro) found that some droplets called empty from
their RNA held high tag counts, probably from neutrophils ([PMID 37973397](https://pubmed.ncbi.nlm.nih.gov/37973397/)).

Ambient RNA carries its origin: in brain single-nucleus data it was mostly neuronal
[caglayan-2022](../records.md#caglayan-2022). A toxicology review notes that chemical exposure kills cells
and adds ambient RNA ([PMID 38645720](https://pubmed.ncbi.nlm.nih.gov/38645720/)). In a pooled screen, however, the ambient
RNA of all conditions mixes before encapsulation, so the RNA alone cannot say which condition lysed.
[souporcell](../records.md#souporcell) estimates one ambient fraction for the whole pool, not
one per source ([PMID 32366989](https://pubmed.ncbi.nlm.nih.gov/32366989/)).

## Risks

- **Random doublets read as interactions.** Expected rates from loading heuristics are too low
  ([PMID 41166377](https://pubmed.ncbi.nlm.nih.gov/41166377/)), and expression-based tools cannot see homotypic doublets.
- **Circularity.** Doublets called from cell-type scores are then tested for enrichment of those same types. Synthetic
  doublets are built from the same data. Ambient RNA can push a singlet over a two-score threshold. QC thresholds fitted on
  the pooled data, then read back as a per-condition readout, measure the threshold as much as the drug.
- **Selection bias.** Condition-dependent removal changes DE (survivors only), composition (relative shares) and pseudobulk
  weights at once ([PMID 32855387](https://pubmed.ncbi.nlm.nih.gov/32855387/),
  [PMID 40205439](https://pubmed.ncbi.nlm.nih.gov/40205439/)). Outlier handling can drop the most cytotoxic well
  ([sccomp](../records.md#sccomp)).
- **Thin evidence.** Most doublet tools are self-evaluated, with one external comparison on sorted pairs
  ([PMID 41583424](https://pubmed.ncbi.nlm.nih.gov/41583424/)). The ambient-hashtag signal rests on one sample
  ([PMID 31266958](https://pubmed.ncbi.nlm.nih.gov/31266958/)).

## Hypotheses worth testing in high-multiplex drug screens

1. **An absolute denominator** ([Spike-in reference cells](../records.md#spike-in-reference-cells), [unbalanced-ot-cell-loss](../records.md#unbalanced-ot-cell-loss)). *Test:* add a fixed number of
   reference cells to every well. Check that the ratio of condition cells to reference cells matches viability, and
   compare DE results with and without a per-condition retained-fraction covariate.
2. **Doublet decomposition** ([rctd-doublet-mode-droplets](../records.md#rctd-doublet-mode-droplets)). *Test:* run RCTD doublet mode on the public sorted DC-T
   doublet data used by ULMnet and compare sensitivity and precision with the published figures.

Whatever the readout, a screen should report, per condition, the barcodes assigned, the singlets kept, the barcodes removed
by each filter, and the doublets by type. Without those numbers no one can tell drug effects from QC effects.

<!-- records:start -->

| Record | Kind | Tier | Side | Recovers / gain | Requires | Paper |
| --- | --- | --- | --- | --- | --- | --- |
| [dsb](#dsb) | tool | `standard` | both | cleaner protein signal, using empty droplets that are usually thrown away | raw-matrix, protein | [paper](https://doi.org/10.1038/s41467-022-29356-8) 2022 |
| [scCODA](#sccoda) | tool | `standard` | neutral | composition changes, including drug-driven depletion, from few samples / own simulations: mean Matthews correlation 0.64, ahead of non-Bayesian methods at low replicate numbers (n = 2 per group scenarios) (self-reported) | filtered-matrix, replicates | [paper](https://doi.org/10.1038/s41467-021-27150-6) 2021 |
| [DoubletDecon](#doubletdecon) | tool | `benchmarked` | both | transitional and progenitor states that synthetic-doublet detectors flag as doublets / mouse bone marrow with validated transitional states: specificity 80.7% before and 95.0% after the rescue step (self-reported) | filtered-matrix | [paper](https://doi.org/10.1016/j.celrep.2019.09.082) 2019 |
| [Cell recovery per condition as a viability readout](#cell-recovery-viability) | method | `published-unbenchmarked` | additive | a viability phenotype from cell counts that would otherwise only set DE power / sci-Plex: viability scores from recovered counts concordant with gold-standard measurements; 52 of 188 compounds (27%) cut viability by 50% or more at the top dose; K562 bosutinib sensitivity confirmed by cell counting (self-reported) | tag-counts, doses-or-time, multiple-conditions | [paper](https://doi.org/10.1126/science.aax6234) 2020 |
| [CIcADA](#cicada) | tool | `published-unbenchmarked` | additive | transcriptional programmes specific to juxtacrine contacts, from doublets / FACS-sorted DC-T doublets: sensitivity 21.7% (in vitro) and 15.1% (in vivo), measured by the ULMnet authors (independent) | filtered-matrix | [paper](https://doi.org/10.1093/bioadv/vbad120) 2023 |
| [Circulating T cell-monocyte complexes](#t-cell-monocyte-complexes) | evidence | `published-unbenchmarked` | additive | evidence that some events removed as doublets are real, condition-dependent biology | protein | [paper](https://doi.org/10.7554/eLife.46045) 2019 |
| [DecontPro](#decontpro) | tool | `published-unbenchmarked` | both | protein-defined cells hidden among RNA-called empty droplets, and cleaner protein signal | raw-matrix, protein | [paper](https://doi.org/10.1093/nar/gkad1032) 2024 |
| [Mitochondrial filtering removes viable, drug-resistant malignant cells](#mito-filter-resistant-cells) | evidence | `published-unbenchmarked` | additive | viable high-mitochondrial malignant cells, including resistant clones, that a fixed 10-20% filter removes / in 10-50% of tumour samples the malignant compartment had twice the high-mito share of the microenvironment, without higher dissociation-stress scores; across CCLE lines higher mito fraction associated with higher IC50 (drug resistance), median mito 4% (glioblastoma) to 14% (head and neck) (independent) | filtered-matrix | [paper](https://doi.org/10.1186/s13059-025-03559-w) 2025 |
| [Neighbor-seq](#neighbor-seq) | tool | `published-unbenchmarked` | additive | cell-cell contact networks and neighbour-dependent expression from undissociated multiplets / FACS-sorted DC-T doublets: sensitivity 52.1% (in vitro) and 29.2% (in vivo) at 98.9-99.2% precision, measured by the ULMnet authors (independent) | filtered-matrix | [paper](https://doi.org/10.1093/nar/gkac333) 2022 |
| [Partial-dissociation sequencing (ProximID, paired-cell sequencing, ClumpSeq)](#partial-dissociation-seq) | design | `published-unbenchmarked` | additive | spatial context and preferential interactions that full dissociation destroys | filtered-matrix, reference | [paper](https://doi.org/10.1038/s41592-018-0009-z) 2018 |
| [PIC-seq](#pic-seq) | method | `published-unbenchmarked` | additive | interaction-specific transcription from cell pairs that QC would discard as doublets / re-use on human kidney allograft CITE-seq (31,203 libraries): 3 of 6 doublet clusters called physically interacting; two analysed clusters at 4.7x and 9.5x the expected artefactual-doublet frequency, mixing-factor regression R2 0.84 and 0.85 (independent) | filtered-matrix, reference | [paper](https://doi.org/10.1038/s41587-020-0442-2) 2020 |
| [propeller (speckle) and Scanpro](#propeller) | tool | `published-unbenchmarked` | neutral | replicate-aware composition shifts per condition | filtered-matrix, replicates | [paper](https://doi.org/10.1093/bioinformatics/btac582) 2022 |
| [sccomp](#sccomp) | tool | `published-unbenchmarked` | neutral | composition and variability changes robust to outlier samples | filtered-matrix, replicates | [paper](https://doi.org/10.1073/pnas.2203828120) 2023 |
| [Spike-in reference cells](#spike-in-reference-cells) | design | `published-unbenchmarked` | both | a per-sample ambient measurement and, in principle, an absolute denominator for cell counts | filtered-matrix, reference | [paper](https://doi.org/10.1186/s13059-020-02006-2) 2020 |
| [Survivor bias in drug-response transcriptomes](#survivor-bias) | evidence | `published-unbenchmarked` | additive | an argument for reading drug effects from lost cells when surviving cells look unchanged | genotypes, multiple-conditions | [paper](https://doi.org/10.1038/s41467-020-17440-w) 2020 |
| [ULMnet](#ulmnet) | method | `published-unbenchmarked` | additive | multiplet composition and contact networks from routine and partially dissociated scRNA-seq / FACS-sorted DC-T doublets: sensitivity 56% in vitro and 39% in vivo at 99.7-99.9% precision, against 52.1%/29.2% for Neighbor-seq and 21.7%/15.1% for CIcADA (self-reported) | filtered-matrix, reference | [paper](https://doi.org/10.3389/fimmu.2025.1722504) 2025 |
| [RCTD doublet mode applied to droplet doublets](#rctd-doublet-mode-droplets) | hypothesis | `hypothesis` | additive | partner identities and proportions for doublets that would otherwise be discarded | filtered-matrix, reference | [paper](https://doi.org/10.1038/s41587-021-00830-w) 2022 |
| [Unbalanced optimal transport to model drug-induced cell loss](#unbalanced-ot-cell-loss) | hypothesis | `hypothesis` | additive | a response model in which killed cells count as part of the effect | filtered-matrix, multiple-conditions | [paper](https://doi.org/10.1016/j.cell.2019.01.006) 2019 |

<!-- records:end -->
