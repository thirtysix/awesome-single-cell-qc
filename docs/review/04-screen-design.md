# Designing the next screen: more usable cells and true replicates per condition

Scope: experimental design for high-multiplex drug (pharmacotranscriptomic) single-cell screens, where many
conditions each get few cells. This page covers what the large screens did, how the platforms and sample tags
compare on cell recovery, and which trade-offs matter. Calling tools for hashtags and genotypes are covered in
the demultiplexing review; statistics for few cells are in the low-cell statistics review.

## The short answer

Four design choices change usable cells and true replicates per condition the most.

1. **Replicate the treatment, not the cell.** Cells from one well are pseudoreplicates; treating them as independent
   inflates type 1 error (Zimmerman 2021; see [squair-2021](../records.md#squair-2021)). sci-Plex treated every compound-dose in duplicate wells
   with positions randomised between plates, and the duplicates agreed at pseudobulk r = 0.99 (Srivatsan 2020,
   [sci-Plex](../records.md#sci-plex)). sci-Plex-GxE repeated each condition in two independent transductions ([sci-Plex-GxE](../records.md#sci-plex-gxe)).
   Tahoe-100M, the largest screen, ran one well per drug-dose, so its median of 1,287 cells per condition comes from a
   single well ([Tahoe-100M](../records.md#tahoe-100m)). See [Independent replicate wells or cultures per condition](../records.md#replicate-wells).
2. **Tag every sample, then load more cells per lane.** With hashtags or genotypes, cross-sample doublets can be
   removed, so lanes can be overloaded. Cell Hashing modelled about 4x more singlets at a matched unresolved multiplet
   rate (Stoeckius 2018, [Cell Hashing](../records.md#cell-hashing)), and an independent cost model found overloading raised power under a fixed
   budget (Schmid 2021, [scPower](../records.md#scpower)). The cost is non-linear: capturing 48% more cells raised doublets by 125% and
   unassigned barcodes by 325% (Mylka 2022, [mylka-2022-hashing-comparison](../records.md#mylka-2022-hashing-comparison)). See [Superloading with sample multiplexing](../records.md#superloading).
3. **Fix at harvest.** Fixed cells stop changing while plates wait. After 4 weeks at -80 C, fixed (10x Flex) and
   cryopreserved (HIVE) leukocytes kept fragile granulocytes better than fresh 10x 3' processing across nine sites
   (ABRF 2026, [abrf-preservation-2026](../records.md#abrf-preservation-2026)). Fixation is also what makes plate-native multiplexing possible
   ([SPLiT-seq / Parse Evercode](../records.md#split-seq-parse), [sci-Plex](../records.md#sci-plex), [10x Chromium Flex](../records.md#10x-flex)).
4. **Measure where cells are lost.** Losses between input and final data are large and differ by platform: about 53%
   of input PBMCs were recovered with 10x against 27% with Parse (Xie 2024), and 42.7% against 16.5% in organoids
   (Sarieva 2026) ([split-pool-input-recovery](../records.md#split-pool-input-recovery)). Nucleus hashing left about 33% of nuclei after its extra washes
   (Gaublomme 2019, [Nucleus hashing](../records.md#nucleus-hashing)). In Tahoe-100M, 95.6 million of 153 million barcoded cells (about 62%) passed
   full filters.

How many cells per condition is enough depends on the question. scPerturb, re-analysing 44 public perturbation datasets,
recommends at least 200-500 cells per perturbation and about 1,000 UMIs per cell to tell a perturbation from control
(Peidli 2024, [scperturb](../records.md#scperturb)). MIX-Seq's downsampling found that tens of cells per condition were enough to estimate
each cell line's mean response (McFarland 2020, [MIX-Seq](../records.md#mix-seq)).

## What the large screens did

| Screen | Design | Conditions | Cells per condition | Replication | How cells are assigned |
|---|---|---|---|---|---|
| sci-Plex (Srivatsan 2020) | 3 lines x 188 compounds x 4 doses (10 nM-10 uM), 24 h | 4,992 treated wells | median 100-200 | duplicate wells, positions randomised between plates | polyA hash oligos on nuclei, sci-RNA-seq3 |
| sci-Plex-GxE (McFaline-Figueroa 2024) | 3,165 guides (522 kinases) x 4 drugs x 2 doses + vehicle, 72 h | 28,242 | about 35 (calculated from 1,052,205 cells) | two independent transductions | nuclear hashes plus guide capture |
| MIX-Seq (McFarland 2020) | pools of 24-99 cancer lines, 13 drugs, 6 and/or 24 h | drug vs DMSO per pool; 11 hashed conditions in a time course | average 130 per line (99-line pool) | lines act as contexts; one culture per condition | SNP demultiplexing; Cell Hashing for time points |
| Tahoe-100M (Zhang 2026; preprint 2025) | about 50 lines per well, 379 drugs x 3 doses (0.05-5 uM), 24 h, 14 plates | 52,886 line-drug-dose | median 1,287 | one well per drug-dose; plate 14 duplicates plate 6 | demuxlet on SNPs; Parse split-pool barcodes |

Sources: Srivatsan 2020; McFaline-Figueroa 2024; McFarland 2020; Tahoe-100M Cell abstract (2026) and bioRxiv preprint
methods (2025). sci-Plex vehicle wells: 96, calculated as 4,608 drug and vehicle wells minus 4,512 drug wells.

What these show:

- **Pooling lines multiplies conditions per well.** Tahoe-100M gets one condition per line in every well, about 50 per
  well. The price is coupling: every line in a well shares that well's handling, so the lines are contexts, not
  replicates of the treatment, and resistant or fast-growing lines take over after cytotoxic drugs. MIX-Seq detected
  97 of 99 lines with at least 20 cells per condition, and Tahoe-100M dropped 3 of 50 lines for consistently low counts
  and excluded conditions under 50 cells ([Cell villages](../records.md#cell-village)).
- **Cell number per well is itself a readout.** sci-Plex estimated viability from hash-based nucleus counts per dose;
  MIX-Seq measured drug-induced shifts in each line's share of the pool. Pooling equal cell numbers per well before
  barcoding, as Tahoe-100M did, equalises conditions but removes that readout unless cells are counted first
  ([count-then-balance-input](../records.md#count-then-balance-input)).
- **Controls were placed differently.** Tahoe-100M kept control-media wells at fixed positions H11 and H12 of each
  plate and compared drugs with DMSO controls from the same plate; the preprint does not state how many DMSO wells each
  plate held. sci-Plex randomised positions between replicate plates. Neither reported a test of well-position effects.

## Platform and reagent comparisons

### Sample tags

Mylka 2022 compared tags against genotype ground truth on four cell lines, their nuclei, PBMCs and mouse tissues
([mylka-2022-hashing-comparison](../records.md#mylka-2022-hashing-comparison)):

| Input | Antibody (TotalSeq) | Lipid / cholesterol oligos | Measure |
|---|---|---|---|
| Cell lines | 1.1% (A), 1.8% (C) | 7% (MULTI-seq LMO), 21% (custom LMO) | barcodes left unassigned |
| Cell lines | about 0.1% | 0.89% (MULTI-seq), 2.68% (custom) | tag swaps among singlets |
| Nuclei | OCA 0.51-0.54 (0.65 after tuning) | OCA 0.84 (cholesterol) | agreement with genotype |
| PBMCs | OCA 0.96 (TotalSeq-B) | OCA 0.93 (10x CellPlex) | agreement with genotype |

Antibodies worked best on whole cells; lipid-based tags worked best on nuclei (cholesterol oligos) and on mouse brain
cells; antibodies did better on spleen and lung. Tags can also rescue cells: in a tumour sample, 90.8% of sequenced neutrophils fell
below the Cell Ranger UMI threshold and were kept by MULTI-seq classification (McGinnis 2019, [MULTI-seq](../records.md#multi-seq)). sci-Plex
labels nuclei with unmodified polyadenylated oligos during lysis in the well; in a human-mouse test it recovered a
median of 270 hash UMIs per cell with 99.1% agreement with species, and the label survived a freeze-thaw cycle
(Srivatsan 2020).

### Loading and doublets

10x guidance quoted by Mylka 2022 puts the multiplet rate near 0.8% per 1,000 captured cells (vendor-reported). Only
multiplets that join different samples are visible to tags, about 1 - 1/N of them for N equal samples (87.5% for
eight samples in Gaublomme 2019). Cell Hashing
superloaded an 8-donor pool and observed 14,002 singlets with 2,974 identifiable multiplets (Stoeckius 2018). Nucleus
hashing loaded 500 to 4,500 nuclei per ul with comparable cell types and genes per nucleus (Gaublomme 2019). MIX-Seq
loaded up to 40,000 cells per 10x channel. scPower notes that observed doublet rates ran above its model, so modelled
gains from overloading are best treated as upper bounds (Schmid 2021).

### Combinatorial indexing and collisions

In split-pool and combinatorial designs the doublet equivalent is a barcode collision, set by cells per final well
relative to the number of barcode combinations.

- SPLiT-seq: 0.1% mouse-human collisions in a 1,758-cell mixing test, and 2.5% expected for 150,000 nuclei with
  48 x 96 x 96 x 14 combinations (Rosenberg 2018, [SPLiT-seq / Parse Evercode](../records.md#split-seq-parse)).
- sci-Plex: varying nuclei per PCR well produced collision rates of 7-23%, matching prediction; well hashes flagged
  95.5% of interspecies collisions and also exposed within-species ones (Srivatsan 2020).
- scifi-RNA-seq: preindexing in cells plus overloaded droplets gave up to 150,000 cells per 10x channel, with
  recovered cells rising linearly from 15,300 to 765,000 loaded nuclei; preindexing itself kept only 53.3% (cell
  lines) and 41.1% (primary) of nuclei (Datlinger 2021, [scifi-RNA-seq](../records.md#scifi-rna-seq)).
- UDA-seq: droplet barcodes first, then plate post-indexing; 1.23% collisions against 6.29% expected from droplets
  alone, with cell recovery of about 57% for 3' RNA (Li 2025, [UDA-seq](../records.md#uda-seq)).
- sci-RNA-seq3: about 2 million nuclei from 61 embryos in one experiment; the optimised protocol costs about 1 cent per
  cell in reagents and uses DSP/methanol fixation, which gave more UMIs than paraformaldehyde (Cao 2019; Martin 2023;
  [sci-RNA-seq3](../records.md#sci-rna-seq3)).
- Tahoe-100M split its barcoded cells into 1,786 sublibraries of about 100,000 cells each.

### Commercial kits

De Simone 2025 ran nine kits on PBMCs from one donor ([de-simone-2025](../records.md#de-simone-2025)). 10x Flex (fixed RNA profiling) ranked best
overall and in the top tier for genes per cell; Flex, 10x 3' and BD gave the most UMIs per cell. Cells recovered
against the targeted number ranged from about 70% (BD) to 122% (Parse); Parse and Scale were run once each because of
kit cost. Recovery against target is not recovery against input: on PBMCs Parse recovered about 27% of input cells
against 53% for 10x, and about 85% of Parse reads carried a valid barcode against 98% for 10x (Xie 2024). On cerebellar
organoids, recovery was 16.5% for Parse against 42.7% for 10x, but more Parse cells passed QC (95.6% against 87.2%) and
fewer showed a stress signature; the authors suggest the stress arises while 10x cells wait unfixed and pass through
the microfluidics (Sarieva 2026). On mouse thymocytes Parse detected about twice as many genes as 10x, while 10x had lower technical
variability (Filippov 2024).

For Flex specifically: its probes do not cover most mitochondrial transcripts, so the usual mitochondrial-fraction
filter loses meaning (ABRF 2026). Core-facility guidance relaying the 10x protocol recommends at least 25,000 cells per
fixation (10x support advises 75,000) and warns that targeting more than about 13,000 cells per sample pushes
multiplets above 5% (EPFL GECF guidelines, 2025). 10x announced in October 2025 a plate-format Flex for up to 384
samples and 100 million cells per week (vendor-reported, not independently tested).

### Fixation and storage

- Methanol: no change in genes or UMIs per cell after storage for weeks (Alles 2017). On hiPSC-derived neural cells it
  kept composition closest to fresh, while DMSO cryopreservation gave the most complex libraries but shifted
  composition and induced stress and apoptosis genes (Gutierrez-Franco 2023). Wohnhaas 2019 preferred DMSO
  cryopreservation in other cell types, so the choice is cell-type dependent ([Methanol fixation](../records.md#methanol-fixation)).
- DSP (reversible crosslinker): fresh against fixed K562 bulk r above 0.93, fixed replicates stored 3 or 7 days r about
  0.97; slightly lower cDNA yield and some 3' bias; fixed cells keep propidium iodide, so viability at fixation can be
  recorded (Attar 2018, [DSP reversible fixation](../records.md#dsp-fixation)).
- FixNCut: DSP fixation of tissue before dissociation preserved composition and reduced stress signatures
  (Jimenez-Gracia 2024, [FixNCut](../records.md#fixncut)).

## Trade-offs: cells, conditions, depth and replicates

**Depth against cells.** Under a fixed budget, shallow sequencing of more cells gave higher power than deep sequencing
of fewer cells across platforms (Schmid 2021), and lower coverage of more individuals raised cell-type eQTL power
(Mandric 2020). For estimating gene distributions, the optimum was about one read per cell per gene (Zhang 2020,
[sequencing-depth-allocation](../records.md#sequencing-depth-allocation)). In scPerturb, the number of significant perturbations stopped rising near 500 UMIs per
cell. Tahoe-100M cells had a median of 1,890 transcripts. Taken together, these results suggest that depth well
beyond about 1,000 UMIs per cell buys less than more cells or more wells for condition-level questions.

**Cells against conditions.** The number of significant perturbations fell as scPerturb subsampled cells per
perturbation, and only some datasets reached saturation at their full cell count. sci-Plex, at a median of 100-200
cells per condition, had 107 of 188 drugs significant by E-test. sci-Plex-GxE ran about 35 cells per gene-by-drug
condition and pooled guides per gene to compensate.

**Conditions against replicates.** Tahoe-100M put its budget into conditions; sci-Plex and sci-Plex-GxE paid for a
second independent well or transduction. Without a second well, the drug effect cannot be separated from that well's
handling. Pseudobulk testing needs the well as its unit (Zimmerman 2021; [squair-2021](../records.md#squair-2021)).

**Lines against replicates.** Pooled lines raise conditions per well and share one environment, which removes
line-by-well confounding (Wells 2023, [Cell villages](../records.md#cell-village)), but they do not replicate the treatment.

**Doses and time points.** Dose series let information be shared across conditions (sci-Plex fitted dose-response
models to estimate the transcriptional potency of HDAC inhibitors). MIX-Seq found DMSO cells did not differ across five time points and pooled them, which
raised control cells per comparison.

## Hypotheses and open questions

- **Scattered vehicle controls.** In bulk drug-testing plates, normalisation broke down above about 20% hits per plate
  when controls sat at the plate edge, while scattered controls with Loess reduced row, column and edge effects
  (Mpindi 2015, simulated 384-well plates). No single-cell study found here measured well-position effects
  ([scattered-vehicle-controls](../records.md#scattered-vehicle-controls)).
- **How many DMSO wells?** sci-Plex used 96 vehicle wells for 4,512 drug wells (calculated from reported totals);
  the Tahoe-100M preprint does not state its DMSO well count. No study justified its number.
- **Count, then balance.** Counting cells per well before pooling equal numbers would keep viability as a readout and
  equalise cells per condition ([count-then-balance-input](../records.md#count-then-balance-input)). Untested.
- **Cytotoxic dropout.** Cells are fewest where drug effects are largest. Seeding more cells in high-dose wells, or
  pooling replicate wells for those doses, has not been evaluated.
- **Nuclei or whole cells for drug response.** sci-Plex works on nuclei; MIX-Seq and Tahoe-100M on whole cells. No
  head-to-head comparison of drug-response signal between nuclei and cells was found.
- **Flex in small wells.** Fixation inputs of 25,000-75,000 cells per sample may exceed what a treated 96-well well
  yields; whether plate-format Flex removes that limit has not been independently reported.

## Ranked recommendations for the next high-multiplex drug screen

1. **Two or more independently treated wells per condition**, with drug and dose positions randomised between replicate
   plates (sci-Plex). Pay for it with depth, not with replication.
2. **Tag every well at harvest and fix.** Cholesterol oligos for nuclei, antibodies for whole cells (Mylka 2022), or
   polyA hash oligos when the readout is sci-RNA-seq (sci-Plex). Use the tags for doublet removal and for counting cells per well.
3. **Target about 200-500 cells per condition and about 1,000 UMIs per cell** when the question is whether a drug
   changes the cell distribution (scPerturb); tens of cells can do for mean-shift profiles (MIX-Seq).
4. **Overload with tags, after a pilot loading series** that measures doublets and unassigned barcodes, since both rise
   faster than cells captured (Mylka 2022).
5. **Pool cell lines only as extra contexts**, balanced at seeding and with genotype references, and never count them
   as replicates.
6. **Log losses at each step**: cells seeded, cells at harvest, cells into barcoding, barcodes passing QC; report
   recovery against input.
7. **Put vehicle wells on every plate, scattered across rows, columns and edges** (hypothesis, from bulk screening).
8. **Pick the platform by input and plex:** Flex for sensitivity and fragile cells when per-sample input is large;
   split-pool kits or sci-RNA-seq3 for 96-384 plate-native samples, accepting lower input recovery.

## Sources

Alles 2017 BMC Biol doi:10.1186/s12915-017-0383-5; Attar 2018 Sci Rep doi:10.1038/s41598-018-20372-7; Cao 2019
Nature doi:10.1038/s41586-019-0969-x; Datlinger 2021 Nat Methods doi:10.1038/s41592-021-01153-z; De Simone 2025 NAR
doi:10.1093/nar/gkae1186; Filippov 2024 BMC Genomics doi:10.1186/s12864-024-10976-x; Gaublomme 2019 Nat Commun
doi:10.1038/s41467-019-10756-2; Gutierrez-Franco 2023 Commun Biol doi:10.1038/s42003-023-04834-x; Jimenez-Gracia 2024
Genome Biol doi:10.1186/s13059-024-03219-5; Kolling (ABRF) 2026 J Biomol Tech doi:10.7171/001c.162768; Li 2025 Nat
Methods doi:10.1038/s41592-024-02586-y; Mandric 2020 Nat Commun doi:10.1038/s41467-020-19365-w; Martin 2023 Nat
Protoc doi:10.1038/s41596-022-00752-0; McFaline-Figueroa 2024 Cell Genomics doi:10.1016/j.xgen.2023.100487; McFarland
2020 Nat Commun doi:10.1038/s41467-020-17440-w; McGinnis 2019 Nat Methods doi:10.1038/s41592-019-0433-8; Mpindi 2015
Bioinformatics doi:10.1093/bioinformatics/btv455; Mylka 2022 Genome Biol doi:10.1186/s13059-022-02628-8; Peidli 2024
Nat Methods doi:10.1038/s41592-023-02144-y; Rosenberg 2018 Science doi:10.1126/science.aam8999; Sarieva 2026 iScience
doi:10.1016/j.isci.2026.114780; Schmid 2021 Nat Commun doi:10.1038/s41467-021-26779-7; Srivatsan 2020 Science
doi:10.1126/science.aax6234; Stoeckius 2018 Genome Biol doi:10.1186/s13059-018-1603-1; Wells 2023 Cell Stem Cell
doi:10.1016/j.stem.2023.01.010; Wohnhaas 2019 Sci Rep doi:10.1038/s41598-019-46932-z; Xie 2024 Int J Mol Sci
doi:10.3390/ijms25073828; Zhang 2020 Nat Commun doi:10.1038/s41467-020-14482-y; Zhang 2026 Cell (Tahoe-100M)
doi:10.1016/j.cell.2026.08.035 and preprint doi:10.1101/2025.02.20.639398; Zimmerman 2021 Nat Commun
doi:10.1038/s41467-021-21038-1. Vendor and core-facility material (self-reported): 10x Genomics press release,
29 October 2025; EPFL Gene Expression Core Facility, Flex (GEM-X) sample guidelines vA.06, 2025.

<!-- records:start -->

| Record | Kind | Tier | Side | Recovers / gain | Requires | Paper |
| --- | --- | --- | --- | --- | --- | --- |
| [Cell Hashing (antibody hashtags)](#cell-hashing) | design | `standard` | additive | cells per lane through superloading, and doublets that RNA-only methods miss / 8-donor PBMC pool superloaded for about 20,000 singlets: modelled unresolved multiplet rate 3.1%, against about 4,000 singlets at the same rate without hashing (described as about 400% more cells for the same cost); observed 14,002 singlets and 2,974 identifiable multiplets (self-reported) | tag-counts, filtered-matrix | [paper](https://doi.org/10.1186/s13059-018-1603-1) 2018 |
| [Independent replicate wells or cultures per condition](#replicate-wells) | design | `standard` | additive | true replicates for pseudobulk testing and an estimate of well-to-well variance / Cells within one sample are pseudoreplicates and treating them as independent inflates type 1 error (Zimmerman 2021, see also [squair-2021](../records.md#squair-2021)); sci-Plex duplicate wells on randomised plates agreed at pseudobulk r = 0.99; sci-Plex-GxE used two independent transductions per condition (independent) | replicates | - |
| [10x Chromium Flex (fixed RNA profiling)](#10x-flex) | design | `benchmarked-sota` | additive | fragile cells and queued samples through fixation and storage, and samples per run through probe barcodes / Independent: best overall of nine commercial kits on PBMCs and top tier for genes per cell (De Simone 2025); fixation retained fragile granulocytes better than fresh 10x 3' across nine sites after 4 weeks at -80 C (ABRF 2026); vendor-reported: up to 384 samples and 100 million cells per week in a 96-well plate format (October 2025 release) (independent) | fastq | - |
| [Methanol fixation](#methanol-fixation) | design | `benchmarked-sota` | additive | cells and states that would degrade while samples wait, including low-RNA cells after storage / Independent (Gutierrez-Franco 2023): on hiPSC-derived neural cells methanol kept cell composition closest to fresh with little expression bias, while DMSO cryopreservation shifted composition and induced stress and apoptosis genes; self-reported (Alles 2017): unchanged genes and UMIs per cell in human-mouse mixtures after storage for weeks (independent) | - | [paper](https://doi.org/10.1186/s12915-017-0383-5) 2017 |
| [MULTI-seq (lipid and cholesterol tags)](#multi-seq) | design | `benchmarked-sota` | additive | low-RNA cells that a UMI threshold would discard, and doublets including transcriptionally similar ones / Independent (Mylka 2022): cholesterol-oligo hashing of nuclei reached overall classification accuracy 0.84 against 0.51-0.65 for antibody nuclei hashing, and lipids beat antibodies on mouse brain cells; self-reported: in a PDX tumour, 90.8% of sequenced neutrophils fell below the Cell Ranger UMI threshold and were kept by MULTI-seq classification (independent) | tag-counts, raw-matrix | [paper](https://doi.org/10.1038/s41592-019-0433-8) 2019 |
| [Nucleus hashing (antibody)](#nucleus-hashing) | design | `benchmarked` | additive | nuclei per lane through overloading with detectable inter-sample multiplets / Loading 500 to 4,500 nuclei per ul gave comparable cell types and genes per nucleus; DemuxEM agreed with demuxlet on 96% of nuclei; estimated multiplet rate 2.8% against 2.7% expected when 7,000 nuclei were loaded (self-reported) | tag-counts, raw-matrix | [paper](https://doi.org/10.1038/s41467-019-10756-2) 2019 |
| [SPLiT-seq / Parse Evercode](#split-seq-parse) | design | `benchmarked` | additive | samples per run (96-384 per commercial kit, vendor-reported) and storage of fixed cells; fewer stressed cells than unfixed droplet capture in one organoid comparison / Independent: about 2x genes per cell against 10x 3' on mouse thymocytes (Filippov 2024); post-QC retention 95.6% against 87.2% and fewer stressed cells than 10x CellPlex on cerebellar organoids (Sarieva 2026); self-reported: 0.1% mouse-human collisions and about $0.01 per cell library preparation (2018) (independent) | fastq, multiple-conditions | [paper](https://doi.org/10.1126/science.aam8999) 2018 |
| [ABRF multisite preservation study 2026](#abrf-preservation-2026) | evidence | `published-unbenchmarked` | neutral | After 4 weeks at -80 C, fixation (Flex) and cryopreservation (HIVE) retained granulocytes, about half of leukocytes, better than fresh 10x 3' processing; Flex showed more cross-site technical variation than the other preserved workflows (independent) | fastq | [paper](https://doi.org/10.7171/001c.162768) 2026 |
| [Cell villages (pooled genotypes in one dish)](#cell-village) | design | `published-unbenchmarked` | additive | donors or lines per well without per-line tags, and removal of well-to-well confounding between lines / Neural progenitors from 44 donors cultured in one shared environment and assigned by Dropulation; the same pooling idea carries 50 cancer lines per well in Tahoe-100M and up to 99 lines in MIX-Seq (self-reported) | genotypes | [paper](https://doi.org/10.1016/j.stem.2023.01.010) 2023 |
| [De Simone et al. 2025 nine-kit comparison](#de-simone-2025) | evidence | `published-unbenchmarked` | neutral | Cell recovery against target ranged from about 70% (BD Rhapsody) to 122% (Parse); 10x Flex top tier for genes per cell and best overall; Flex, 10x 3' and BD gave the highest UMIs per cell (independent) | fastq | [paper](https://doi.org/10.1093/nar/gkae1186) 2025 |
| [DSP reversible fixation](#dsp-fixation) | design | `published-unbenchmarked` | additive | the treated state at the moment of fixation, and a viability record because fixed cells keep propidium iodide / K562 cells: fresh against fixed bulk r above 0.93; fixed replicates stored 3 or 7 days r about 0.97, comparable to fresh replicates; less cell-to-cell variation in cDNA yield than fresh cells (self-reported) | - | [paper](https://doi.org/10.1038/s41598-018-20372-7) 2018 |
| [FixNCut](#fixncut) | design | `published-unbenchmarked` | additive | cells and states lost or distorted during dissociation and transport / Preserved RNA integrity, library complexity and cell composition in human and mouse tissues while reducing stress-related signatures, on 10x 3' v3.1 (self-reported) | - | [paper](https://doi.org/10.1186/s13059-024-03219-5) 2024 |
| [Input-to-output recovery, split-pool versus droplet](#split-pool-input-recovery) | evidence | `published-unbenchmarked` | neutral | PBMCs (Xie 2024): about 53% of input cells recovered with 10x against about 27% with Parse, valid-barcode reads about 98% against 85%; cerebellar organoids (Sarieva 2026): 42.7% against 16.5%, with post-QC retention 87.2% against 95.6% (independent) | fastq | [paper](https://doi.org/10.3390/ijms25073828) 2024 |
| [MIX-Seq](#mix-seq) | design | `published-unbenchmarked` | additive | cell lines and conditions per lane without per-line tags; empty droplets and doublets recognised as SNP mixtures / 99-line trametinib pool: average 130 cells per line per condition, 97 of 99 lines with at least 20 cells; 0 of 84,869 cells assigned to an out-of-pool line from a 494-line reference; classification robust with 50-100 detected SNP sites; downsampling suggested tens of cells per condition suffice for a per-line response profile; up to 40,000 cells loaded per 10x channel (self-reported) | genotypes, bam, multiple-conditions | [paper](https://doi.org/10.1038/s41467-020-17440-w) 2020 |
| [sci-Plex](#sci-plex) | design | `published-unbenchmarked` | additive | conditions per experiment, collision (doublet) flags from well hashes, and cell number per well as a viability readout / 4,992 independently treated wells (188 compounds x 4 doses x 3 cell lines, in duplicate) and 649,340 cells in one experiment; median 100-200 cells per condition; replicate-well pseudobulk Pearson r = 0.99; hashes flagged 95.5% of interspecies collisions at collision rates of 7-23% (self-reported) | fastq, tag-counts, multiple-conditions, doses-or-time | [paper](https://doi.org/10.1126/science.aax6234) 2020 |
| [sci-Plex-GxE](#sci-plex-gxe) | design | `published-unbenchmarked` | additive | true replicates (independent transductions) and hash-based doublet removal in a gene-by-drug grid / 1,052,205 cells over 28,242 conditions (14,121 gene-by-environment combinations x 2 independent transductions); 94.3% of cells assigned to a condition after doublet removal; about 35 cells per condition on average (calculated from the reported totals); pilot: 94.4% of 18,585 cells assigned to a well (self-reported) | fastq, tag-counts, multiple-conditions, doses-or-time, replicates | [paper](https://doi.org/10.1016/j.xgen.2023.100487) 2024 |
| [sci-RNA-seq3](#sci-rna-seq3) | design | `published-unbenchmarked` | additive | cells per experiment at a reagent cost near one cent per cell; reverse-transcription wells act as sample barcodes / About 2 million nuclei from 61 mouse embryos in one experiment (2019); optimised protocol (Martin 2023): reagent cost about 1 cent per cell or less, DSP/methanol fixation gives more UMIs than paraformaldehyde, and new buffers reduce nuclei loss during washes (self-reported) | fastq | [paper](https://doi.org/10.1038/s41586-019-0969-x) 2019 |
| [scifi-RNA-seq](#scifi-rna-seq) | design | `published-unbenchmarked` | additive | cells per channel: transcriptomes from multi-cell droplets are kept instead of discarded as doublets / Up to 150,000 cells per Chromium channel and over 1 million per chip; 100-fold overloading kept a stable emulsion; recovered transcriptomes scaled linearly from 15,300 to 765,000 loaded nuclei; no loss of complexity in droplets holding up to 15 nuclei (self-reported) | fastq | [paper](https://doi.org/10.1038/s41592-021-01153-z) 2021 |
| [scPerturb](#scperturb) | evidence | `published-unbenchmarked` | neutral | Significant perturbations fell as cells per perturbation were subsampled, and significance saturated near 500 UMIs per cell; guideline of at least 200-500 cells per perturbation and about 1,000 UMIs per cell; sci-Plex 3: 107 of 188 drugs significant by E-test (independent) | multiple-conditions | [paper](https://doi.org/10.1038/s41592-023-02144-y) 2024 |
| [scPower](#scpower) | tool | `published-unbenchmarked` | neutral | power per unit budget by choosing samples, cells and depth together / Across platforms, shallow sequencing of many cells gave higher overall power than deep sequencing of fewer cells; with doublet detection, overloading lanes increased power despite discarding doublets (self-reported) | replicates | [paper](https://doi.org/10.1038/s41467-021-26779-7) 2021 |
| [Sequencing depth allocation (one read per cell per gene)](#sequencing-depth-allocation) | evidence | `published-unbenchmarked` | neutral | The optimal allocation gave about half the relative error of the depth used in a standard 10x PBMC 4k dataset (self-reported) | filtered-matrix | [paper](https://doi.org/10.1038/s41467-020-14482-y) 2020 |
| [Superloading with sample multiplexing](#superloading) | design | `published-unbenchmarked` | additive | singlets per lane and per unit cost / scPower cost-power model (independent of the hashing authors): with doublet detection, overloading lanes raised DE and eQTL power under a fixed budget even after doublets were discarded; Cell Hashing (self-reported, modelled): about 4x more singlets at a matched unresolved multiplet rate (independent) | tag-counts, genotypes | - |
| [Tahoe-100M](#tahoe-100m) | design | `published-unbenchmarked` | additive | cells per condition at atlas scale: each drug-dose well yields one condition per pooled line / Preprint figures: 153 million barcoded cells, 95.6 million (about 62%) passed full filters; 52,886 line-drug-dose conditions with a median of 1,287 cells each; demuxlet benchmark accuracy above 98% with over 90% of cells called singlets; median correlation 0.975 for matched versus 0.915 for unmatched conditions (self-reported) | fastq, genotypes, multiple-conditions, doses-or-time | [paper](https://doi.org/10.1016/j.cell.2026.08.035) 2026 |
| [UDA-seq](#uda-seq) | design | `published-unbenchmarked` | additive | cells and samples per channel at a low collision rate / Collision rate 1.23% with 96-well post-indexing against 6.29% expected from the droplet barcode alone; over 100,000 cells from three dozen frozen clinical biopsies in one channel (self-reported) | fastq | [paper](https://doi.org/10.1038/s41592-024-02586-y) 2025 |
| [Count cells per well, then balance input](#count-then-balance-input) | hypothesis | `hypothesis` | additive | cells per condition in cytotoxic wells, and the viability readout that equal-input pooling would otherwise erase / No direct test; sci-Plex used hash-based nucleus counts per well as a viability measure, Tahoe-100M put roughly equal cell numbers per sample into barcoding, and scPerturb found that unequal cells per condition bias E-distance | tag-counts, doses-or-time | - |
| [Scattered vehicle controls and randomised plate layout](#scattered-vehicle-controls) | hypothesis | `hypothesis` | neutral | unbiased within-plate controls and the ability to separate plate position from drug effect / Bulk high-throughput screening, not single-cell: with active-drug plates above about 20% hit rate, normalisation using edge-placed controls failed while scattered controls plus Loess reduced row, column and edge effects (Mpindi 2015, simulated 384-well plates); not yet measured for single-cell transcriptomic readouts (independent) | multiple-conditions, replicates | - |

<!-- records:end -->
