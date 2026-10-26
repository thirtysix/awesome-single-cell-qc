# Salvaging cells and signal in multiplexed single-cell experiments: overview

Highly multiplexed single-cell experiments, drug screens above all, spend their cells thinly: hundreds of
conditions, tens to a few hundred cells each, often one well per condition. Every step between the plate and the
count matrix loses cells, and in published comparisons the losses are large: fixed QC cut-offs alone kept a median
69.4% of cells where cluster-aware thresholds kept up to 95.4% (self-reported, [ddqc](../records.md#ddqc)), weak hashing left 7 to 33% of cells
untagged ([mylka-2022-hashing-comparison](../records.md#mylka-2022-hashing-comparison)), and only 16.5 to 53% of input cells reached the final data across
platforms ([split-pool-input-recovery](../records.md#split-pool-input-recovery)). The losses are also not random. Hashing fails more often in dying and
some cell types ([mylka-2022-hashing-comparison](../records.md#mylka-2022-hashing-comparison), [hadge](../records.md#hadge)), mitochondrial filters remove viable and even
drug-resistant malignant cells ([mito-filter-resistant-cells](../records.md#mito-filter-resistant-cells)), and drugs change how much RNA a cell holds
(PMID 34159316). In a
screen, a loss that differs by condition is a bias before it is a cost.

This overview summarises five literature reviews written for this hub in October 2026 (129 records and 38 benchmark
studies, every identifier fetched and checked). It is organised by pipeline stage: what is standard, what has won an independent
benchmark, what is published but untested, and what is only proposed. The short version:

1. **Recover tagged cells with a better caller, not a looser one.** Per-cell normalisation of tag counts and
   RNA-aware or free-tag-aware callers recover most cells wrongly called negative ([sayed-2025-hashtag-benchmark](../records.md#sayed-2025-hashtag-benchmark),
   [demuxmix](../records.md#demuxmix), [deMULTIplex2](../records.md#demultiplex2)); genotypes rescue most of the rest when samples differ genetically ([hadge](../records.md#hadge)).
2. **Keep cells by replacing single-metric cut-offs with evidence that separates damage from biology:** test barcodes
   against the ambient profile ([EmptyDrops](../records.md#emptydrops)), compute thresholds within cell type and batch ([ddqc](../records.md#ddqc),
   [miQC](../records.md#miqc)), use the nuclear fraction for damage ([DropletQC](../records.md#dropletqc)), and correct ambient RNA instead of discarding
   mixed profiles ([CellBender remove-background](../records.md#cellbender), [DecontX](../records.md#decontx)).
3. **Borrow strength, do not invent replicates.** Pseudobulk with the culture or well as the unit leads every
   independent benchmark ([squair-2021](../records.md#squair-2021), [junttila-2022](../records.md#junttila-2022)); weighting small samples ([dreamlet](../records.md#dreamlet)), empirical
   Bayes ([Empirical Bayes moderation](../records.md#empirical-bayes-moderation)), dose as a trend ([Dose-response modelling across doses](../records.md#dose-response-modelling)) and multivariate shrinkage
   across conditions ([mashr](../records.md#mashr)) add power without pretending cells are replicates ([cell-subsample-pseudoreplicates](../records.md#cell-subsample-pseudoreplicates)).
4. **Design for replicates and for fixing early.** Duplicate wells with randomised positions ([sci-Plex](../records.md#sci-plex),
   [Independent replicate wells or cultures per condition](../records.md#replicate-wells)), fixation at harvest ([10x Chromium Flex](../records.md#10x-flex), [Methanol fixation](../records.md#methanol-fixation)) and tagged superloading
   ([Superloading with sample multiplexing](../records.md#superloading), modelled rather than benchmarked) change usable cells and true replicates more than any
   downstream tool.
5. **Treat what is discarded as data.** Cells lost per condition track toxicity ([Cell recovery per condition as a viability readout](../records.md#cell-recovery-viability)),
   survivors can hide a drug's effect ([survivor-bias](../records.md#survivor-bias)), and doublets can be real cell contacts ([PIC-seq](../records.md#pic-seq),
   [Neighbor-seq](../records.md#neighbor-seq)). None of these has been tested as a readout in a high-multiplex drug screen.

## By stage

| Stage | Standard | Independently benchmarked best | Published, not benchmarked | Proposed |
|---|---|---|---|---|
| Hashing demultiplexing | [HTODemux](../records.md#htodemux), [HashSolo](../records.md#hashsolo), [hashedDrops](../records.md#hasheddrops) | [demuxmix](../records.md#demuxmix) (best overall in [howitt-2023-hto-benchmark](../records.md#howitt-2023-hto-benchmark)); [deMULTIplex2](../records.md#demultiplex2) and per-cell CLR ([sayed-2025-hashtag-benchmark](../records.md#sayed-2025-hashtag-benchmark)); [GMM-Demux](../records.md#gmm-demux), [demuxEM](../records.md#demuxem). Mixed: [MULTIseqDemux / deMULTIplex](../records.md#multiseqdemux), [cellhashR](../records.md#cellhashr) | [CMDdemux](../records.md#cmddemux), [Tag-guided rescue of low-RNA cells](../records.md#tag-guided-cell-rescue) | [expression-label-recovery](../records.md#expression-label-recovery) |
| Genotype demultiplexing | [demuxlet / freemuxlet](../records.md#demuxlet) | [vireo](../records.md#vireo), [Demuxalot](../records.md#demuxalot), [souporcell](../records.md#souporcell) ([Demuxafy](../records.md#demuxafy), [fu-2025-snrna-genetic-benchmark](../records.md#fu-2025-snrna-genetic-benchmark), [weber-2021-cancer-genetic-demux](../records.md#weber-2021-cancer-genetic-demux)) | hashing + genotype rescue: [hadge](../records.md#hadge), [HTOreader and hybrid hashing-genotype demultiplexing](../records.md#htoreader-hybrid), [demuxSNP](../records.md#demuxsnp) | |
| Cell calling | Cell Ranger caller, [EmptyDrops](../records.md#emptydrops) | none (no independent benchmark of cell callers) | [CB2](../records.md#cb2) | |
| Ambient RNA | [SoupX](../records.md#soupx) | [CellBender remove-background](../records.md#cellbender), [DecontX](../records.md#decontx) ([janssen-2023](../records.md#janssen-2023), [cargnelli-2026](../records.md#cargnelli-2026), [nie-2026](../records.md#nie-2026)). Mixed: [scAR](../records.md#scar) removes most but over-corrects | | |
| QC thresholds | [MAD-based adaptive QC thresholds](../records.md#mad-adaptive-qc) | [pipeComp](../records.md#pipecomp) (only independent test of stringency) | [miQC](../records.md#miqc), [ddqc](../records.md#ddqc), [MitoChontrol](../records.md#mitochontrol) | [condition-aware-qc-audit](../records.md#condition-aware-qc-audit) |
| Damaged cells | mito cut-off | | [DropletQC](../records.md#dropletqc), [oflanagan-2019](../records.md#oflanagan-2019), [mito-filter-resistant-cells](../records.md#mito-filter-resistant-cells) | |
| Doublets (RNA) | Scrublet, DoubletFinder | [scDblFinder](../records.md#scdblfinder) ([xi-li-2021](../records.md#xi-li-2021)), but weak on single-lineage data ([singletcode-2024](../records.md#singletcode-2024)) | | |
| Statistics with few cells | [Pseudobulk differential expression](../records.md#pseudobulk-de), [Empirical Bayes moderation](../records.md#empirical-bayes-moderation), [voomWithQualityWeights](../records.md#voom-quality-weights) | pseudobulk ([squair-2021](../records.md#squair-2021), [junttila-2022](../records.md#junttila-2022)). Mixed: [NEBULA](../records.md#nebula) (best in one simulation, behind pseudobulk in another) | [dreamlet](../records.md#dreamlet), [mashr](../records.md#mashr), [TRADE](../records.md#trade), [MrVI](../records.md#mrvi), [CPA and chemCPA](../records.md#cpa) | [pooled-variance-unreplicated-drugs](../records.md#pooled-variance-unreplicated-drugs), [control-well-null](../records.md#control-well-null) |
| Screen design | [Cell Hashing](../records.md#cell-hashing), [Independent replicate wells or cultures per condition](../records.md#replicate-wells) | [10x Chromium Flex](../records.md#10x-flex), [Methanol fixation](../records.md#methanol-fixation), [MULTI-seq](../records.md#multi-seq). Mixed: [SPLiT-seq / Parse Evercode](../records.md#split-seq-parse) | [Superloading with sample multiplexing](../records.md#superloading), [sci-Plex](../records.md#sci-plex), [MIX-Seq](../records.md#mix-seq), [Tahoe-100M](../records.md#tahoe-100m), [scifi-RNA-seq](../records.md#scifi-rna-seq) | [scattered-vehicle-controls](../records.md#scattered-vehicle-controls), [count-then-balance-input](../records.md#count-then-balance-input) |
| Discarded data | | | [PIC-seq](../records.md#pic-seq), [Neighbor-seq](../records.md#neighbor-seq), [Cell recovery per condition as a viability readout](../records.md#cell-recovery-viability), [sccomp](../records.md#sccomp) | [rctd-doublet-mode-droplets](../records.md#rctd-doublet-mode-droplets) |

Tiers follow the hub schema. "Benchmarked best" means best or tied best in at least one study by other authors
(38 benchmark studies are listed in the catalog); "mixed" means independently evaluated without being best, or with
conflicting results. Several wins rest on one benchmark, and some conflict: [demuxmix](../records.md#demuxmix) led one hashing benchmark
but failed on imbalanced xenograft pools in another.

## What cuts across the stages

**Losses depend on the condition.** Every stage loses more cells from stressed, damaged or atypical cells: weak
tags in dying cells ([mylka-2022-hashing-comparison](../records.md#mylka-2022-hashing-comparison)), low-RNA treated cells at cell calling, high-mito resistant
cells at QC ([mito-filter-resistant-cells](../records.md#mito-filter-resistant-cells)). In a drug screen this means a QC step can remove part of a drug's
effect, or create one. The cheapest protection is an audit: cells kept per condition at each step, tested for
dependence on the condition ([condition-aware-qc-audit](../records.md#condition-aware-qc-audit)).

**Hashing is an independent witness.** Tags measure that a cell was present independently of its RNA, so they help
decide whether a QC-flagged cell is damaged or merely different, and they can rescue cells below RNA thresholds
([MULTI-seq](../records.md#multi-seq), [Tag-guided rescue of low-RNA cells](../records.md#tag-guided-cell-rescue)).

**More cells per condition is not more replicates.** Splitting one well's cells into groups reproduces the bias and
false discoveries of cell-level tests ([cell-subsample-pseudoreplicates](../records.md#cell-subsample-pseudoreplicates), [squair-2021](../records.md#squair-2021)). With one culture per
condition, a p-value says that two wells differ, not that a drug works. The large screens differ sharply here:
[sci-Plex](../records.md#sci-plex) used duplicate wells, [Tahoe-100M](../records.md#tahoe-100m) one well per drug and dose.

**Models are not a substitute for replicates.** Deep perturbation models have not beaten additive or linear
baselines in independent comparisons ([ahlmann-eltze-2025](../records.md#ahlmann-eltze-2025)), and imputation mostly erases small effects
([imputation-de-evidence](../records.md#imputation-de-evidence)).

## The evidence gaps

- No step of the salvage pipeline has been benchmarked on drug-treated cells.
- No independent benchmark of cell callers or of adaptive QC tools exists.
- No hashing benchmark goes beyond about 24 tags or tests row-by-column (combinatorial) tag designs.
- No study compares minimum-cell cut-offs with weighting by cell number, or tests signals in discarded
  barcodes as readouts in drug screens.

These gaps are where a well-designed screen could contribute evidence of its own.

## Chapters

- [01. Recovering cells at demultiplexing](01-demux-recovery.md)
- [02. Keeping cells at cell calling and QC; damaged cells](02-calling-qc-damaged.md)
- [03. Statistics with few cells](03-low-cell-stats.md)
- [04. Designing the next screen](04-screen-design.md)
- [05. Signal in discarded barcodes](05-discarded-data.md)

The chapters above focus on salvage. The next three cover every QC stage, additive and subtractive, at
catalog depth:

- [11. Alignment, quantification, cell calling and ambient RNA](11-quant-calling-ambient.md)
- [12. Doublets, cell-cycle and stress signatures, batch and lane effects](12-doublets-stress-batch.md)
- [13. QC metrics, guides and modality-specific QC](13-metrics-guides-multimodal.md)

The concept map follows QC choices into the rest of the analysis, at a lighter depth:

- [20. Concept map](20-concept-map.md)
- [21. Preprocessing concepts](21-concepts-preprocessing.md)
- [22. Downstream concepts](22-concepts-downstream.md)
