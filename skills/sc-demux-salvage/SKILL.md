---
name: sc-demux-salvage
description: >-
  Recover cells that demultiplexing throws away in hashed or genotype-pooled single-cell experiments:
  diagnose tag quality, re-call with per-cell normalisation and several callers, rescue negatives with
  genotypes, screen hashing "doublets" that are one cell, keep confidently tagged low-RNA barcodes, and
  carry the few cells left per condition into weighted pseudobulk. Evidence-ranked from the
  awesome-single-cell-qc hub. Use when the user says "too many negatives", "hashing failed", "lost cells
  at demultiplexing", "HTODemux doublets", "rescue hashtag negatives", "demuxmix / deMULTIplex2 / vireo /
  souporcell / hadge", "which hashing caller", "cell hashing drug screen", "superloading", or has a
  multiplexed run with low singlet yield.
meta:
  domain: [sc-preprocess-qc]
  status: draft
  version: 0.1
  inputs: [tag_counts, rna_counts, bam_optional]
  outputs: [per_cell_calls_tsv, recovery_table_md]
  compute_tier: local
  citations: ["Howitt 2023 hashing benchmark", "Sayed 2025 hashtag normalisation benchmark", "Curion 2024 hadge", "Neavin 2024 Demuxafy", "Mylka 2022 hashing chemistries"]
  records: [howitt-2023-hto-benchmark, sayed-2025-hashtag-benchmark, mylka-2022-hashing-comparison, htodemux, multiseqdemux, hashsolo, hasheddrops, demuxmix, demultiplex2, demuxem, gmm-demux, cellhashr, cmddemux, vireo, souporcell, demuxlet, demuxalot, demuxafy, hadge, htoreader-hybrid, demuxsnp, tag-guided-cell-rescue, expression-label-recovery, superloading, mix-seq, dreamlet, muscat]
  provenance: {origin: original, note: "distilled from docs/review/01-demux-recovery.md and 03-low-cell-stats.md of the hub"}
---

# Salvaging cells at demultiplexing

On well-hashed pools every caller agrees and little is lost (mean F 0.88 to 0.94 against genotype
truth, Howitt 2023). On weak hashing, callers range from F 0 to 0.68 on the same droplets while
genotypes still place 90% as singlets. Losses are not random: hashing failure tracks cell type and
state, and RNA quality is largely uncorrelated with tag quality, so a weak tag is not a bad cell.

The full evidence, with numbers and sources, is in the hub repository (awesome-single-cell-qc):
`docs/review/01-demux-recovery.md` (callers, rescue) and `docs/review/03-low-cell-stats.md` (what to
do with the cells you keep). Record ids below in `[[...]]` are rows of its `data/catalog.json`.

## Rescue order (ranked by gain per unit of effort)

1. **Diagnose before choosing.** Per tag: count distribution (log scale) and a tag-space embedding.
   Per condition: negatives, doublets, median tag UMIs. Small, even losses: stop here. Large or
   condition-specific losses: continue.
2. **Re-call with per-cell normalisation and more than one caller.** HTODemux on per-cell CLR
   (Seurat `NormalizeData(margin = 2)`), [[demuxmix]] with the RNA covariate, [[demultiplex2]].
   Keep agreements; inspect disagreements. Per-cell normalisation recovered 56 to 97% of the cells
   wrongly called negative for the most depth-variable tag (Sayed 2025). Little gain on clean data.
3. **Add genotypes when the pool holds more than one donor or cell line.** [[vireo]] or
   [[souporcell]] (no reference), [[demuxalot]] (with reference genotypes, fewest errors in
   [[demuxafy]]); rescue with [[hadge]], [[htoreader-hybrid]] or [[demuxsnp]]. hadge rescued 89.7%
   of hashing negatives in one dataset. Genotype recovers the line, not the treatment: a rescued
   cell gets a condition only if each line had one condition in that pool.
4. **Keep confidently tagged low-RNA barcodes for review** before a UMI floor removes them
   ([[tag-guided-cell-rescue]]). Treated cells may shrink; MULTI-seq kept 90.8% of xenograft
   neutrophils this way.
5. **Expression-based assignment for identity only.** Cell line or cell type: fine. Treatment:
   circular, it inflates the effect and hides non-responders ([[expression-label-recovery]]).
6. **Design the next run for recovery.** Antibody tags for intact cells, lipid or cholesterol tags
   for nuclei and brain (Mylka 2022); balanced loading; enough tag reads. Where hashing is the
   bottleneck, genotype pooling ([[mix-seq]]) or well-barcoded chemistry avoids tag loss.
   [[superloading]] needs tags or genotypes and leaves same-sample doublets (about 1/N) undetected.

## What cannot be rescued
- A true cross-condition doublet: its RNA is a mixture of two treatments. Hashing only sees doublets
  that differ in tag, so every detectable doublet is cross-sample.
- Hashing negatives that are not cells: check UMIs, mito and whether their best-guess sample matches
  their RNA identity better than chance before rescuing.

## Caller notes (independent benchmarks only)
- [[demuxmix]] best overall in Howitt 2023; [[htodemux]] and [[gmm-demux]] close behind.
- Two-peak callers (BFF in [[cellhashr]], deMULTIplex) collapse on weak tags.
- [[hashsolo]] leaves few negatives but passes 30 to 60% of genetic doublets as singlets.
- Lowering [[hasheddrops]]'s threshold raised F in 4 of 6 batches and doubled doublet leakage.
- On nuclei, [[multiseqdemux]] and [[demuxem]] matched genotype best; caller choice alone swung
  yield from almost nothing to almost everything (Curion 2024).
- Self-reported wins in a tool's own paper do not count as benchmarks here.

## Few cells left per condition
Pseudobulk per well and cell type; fit one model across wells with plate as a covariate; keep small
wells with precision weights ([[dreamlet]], voomWithQualityWeights) instead of a hard cell floor, and
apply any floor per analysed group, not by dropping a whole condition. [[muscat]] for the
pseudobulk framework. Ranked list: `docs/review/03-low-cell-stats.md`, last section.
