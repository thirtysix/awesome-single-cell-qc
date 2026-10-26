# Statistics with few cells: more signal per cell and per condition

*Scope: what to do statistically when a condition has few cells, few replicates, or only one culture,
with high-multiplex drug screens as the lead case. Literature checked to October 2026. Every PMID and DOI below
was resolved against PubMed, Crossref or DataCite.*

## The short answer

Most of the extra signal available from a low-cell condition comes from borrowing information, not from squeezing
individual cells harder. Borrowing works across genes (empirical Bayes variance moderation), across the conditions of
a screen (one shared model, doses as a trend, multivariate shrinkage), and across the genes of a program (footprint
scores). None of it creates replication. The unit of inference has to stay the independent culture, well or donor,
and in benchmarks the methods that respect that unit are both the best calibrated and the most concordant with bulk
RNA-seq. Three findings carry most of the weight:

- Across 18 datasets with matched bulk RNA-seq, all six top-ranked of 14 DE methods were pseudobulk methods, and
  cell-level methods called hundreds of DE genes between randomly assigned replicates with no perturbation
  (Squair 2021, PMID 34584091) <a id="squair-2021"></a>[squair-2021](../records.md#squair-2021).
- Splitting cells into random groups and calling them replicates brought the bias and the false discoveries back:
  pseudo-replicates shrank variance most for highly expressed genes across 46 datasets (Squair 2021, PMID 34584091).
  This is the split-well design many drug screens use.
- Deep perturbation models have not yet beaten additive or linear baselines in independent benchmarks
  (Ahlmann-Eltze 2025, PMID 40759747), and imputation mostly erases small effects (Hou 2020, PMID 32854757), so
  neither is a substitute for replicate-level statistics in a screen whose effects are often small.

## Standard practice

<a id="pseudobulk-de"></a>**Pseudobulk.** Counts are summed per replicate sample and cell type, then tested with bulk tools
(edgeR, DESeq2, limma-voom) [Pseudobulk differential expression](../records.md#pseudobulk-de). The cross-modality best-practice review states that pseudobulk methods
with sum aggregation, and mixed models such as MAST with a random effect, were superior to naive cell-level tests such
as the Wilcoxon test (Heumos 2023, [heumos-2023](../records.md#heumos-2023)). Earlier work reached the same conclusion with aggregateBioVar:
naive tests inflate the FDR when expression varies between subjects (Thurman 2021, PMID 33970215).

<a id="muscat"></a>**muscat** packages pseudobulk and mixed-model tests plus a simulator that later benchmarks reuse
(Crowell 2020, PMID 33257685) [muscat](../records.md#muscat). Its `pbDS` default excludes any cluster-sample with fewer than 10 cells.

<a id="empirical-bayes-moderation"></a>**Empirical Bayes moderation** is the oldest and most reliable way to gain power
with 2 to 3 replicates. limma shrinks each gene's variance toward a trend fitted across all genes (Smyth 2004, PMID
16646809; Ritchie 2015, PMID 25605792); edgeR does the same for dispersions, and edgeR v4 revised its
quasi-likelihood method to improve accuracy for small counts (Chen 2025, PMID 39844453); apeglm shrinks noisy fold
changes (Zhu 2019, PMID 30395178) [Empirical Bayes moderation](../records.md#empirical-bayes-moderation). It borrows across genes, not across conditions, and
it cannot moderate a variance that was never estimated: one culture per condition leaves zero residual degrees of
freedom for that condition.

<a id="voom-quality-weights"></a>**Sample weights instead of removal.** limma's `voomWithQualityWeights` estimates a
variance factor per sample and down-weights noisy samples rather than discarding them, which its authors report gives
more power and fewer false discoveries than either removing or equally weighting such samples (Liu 2015, PMID
25925576) [voomWithQualityWeights](../records.md#voom-quality-weights).

<a id="minimum-cells-rules"></a>**Minimum-cells rules.** Floors such as muscat's 10 cells or dreamlet's 5 cells per
sample (with at least 4 samples per cluster) are software defaults [Minimum-cells rules for pseudobulk samples](../records.md#minimum-cells-rules). The only direct evidence
found is a matched scRNA-seq and bulk comparison of the same purified cells: about 2,000 cells per cluster recovered
most DEGs with modest bulk differences, while 50 to 100 cells recovered most DEGs with extremely small bulk p-values or
abundance above a few hundred TPM (Liu 2023, PMID 37394518). That study compares cell populations from one aliquot, so
it says how many cells are needed to see strong effects, not how many replicates are needed to trust them.

<a id="mixscape"></a>**Responder identification in CRISPR screens.** Mixscape subtracts each targeted cell's 20 nearest
control neighbours to form a perturbation signature, then classifies cells as perturbed or escaping; in its ECCITE-seq
screen 115 of 278 IFNGR2-targeted cells escaped (Papalexi 2021, PMID 33649593) [Mixscape](../records.md#mixscape). The best-practice review
lists it for perturbation screens (Heumos 2023, [heumos-2023](../records.md#heumos-2023)). Drug responses are graded rather than binary; the
perturbation-response score models partial responses (Song 2025, PMID 40011559).

## Benchmarked state of the art

<a id="junttila-2022"></a>**Pseudobulk is the benchmark leader.** In an independent comparison of 18 methods, pseudobulk
methods had the highest average AUROC and clearly the best F1; naive cell-level methods had the highest sensitivity
but many false positives, and modelling subjects as latent variables did not fix them (Junttila 2022, PMID 35880426)
[junttila-2022](../records.md#junttila-2022). Sum aggregation generally beat mean, and sensitivity rose with the number of subjects for every method.
A 2025 benchmark of DESeq2, MAST, DREAM, scVI, permutation, distinct, the t-test and hierarchical bootstrapping found
no single-cell-specific method better than pseudobulk DESeq2 on individual datasets, and recommended DREAM as a
quality and runtime compromise at atlas scale (Hafner 2025, PMID 40794957). For data with batches, modelling batch as a
covariate beat analysing batch-corrected data across 46 workflows (Nguyen 2023, PMID 36944632).

<a id="pseudobulk-vs-mixed-debate"></a>**Mixed models: close, contested.** Zimmerman and colleagues found pseudobulk
conservative and underpowered relative to generalized linear mixed models with a random effect per individual
(Zimmerman 2021, PMID 33531494). Re-running their simulation with the Matthews correlation coefficient, Murphy and
Skene found pseudobulk mean had sensitivity above 0.9 at equal type 1 error while every other method was below 0.9,
across 5 to 40 individuals and 50 to 500 cells (Murphy 2022, PMID 36550119), though they attribute the mean-over-sum
advantage to a missing normalisation step in the simulator. The reply argues that MCC can reward tests whose type 1
error exceeds 0.50 (Zimmerman 2022, PMID 36550147) [pseudobulk-vs-mixed-debate](../records.md#pseudobulk-vs-mixed-debate). Lee 2024 narrowed the gap
analytically: count pseudobulk with the right offset has the same point estimates and standard errors as a GLMM and
runs more than 10 times faster (Lee 2024, PMID 39115884).

<a id="nebula"></a>**NEBULA** is the one mixed-model tool that topped an independent benchmark: NEBULA-HL and glmmTMB
outperformed 10 other methods, pseudobulk included, in a 12-method simulation of multi-subject 10x data (Gagnon 2022,
PMID 35743881) [NEBULA](../records.md#nebula). Its own authors note that tests of a subject-level variable were highly sensitive to the
subject variance estimate when subjects were few (He 2021, PMID 34040149), which is exactly the low-replicate case.

## Published but not independently benchmarked

<a id="dreamlet"></a>**dreamlet: keep small samples, weight them.** dreamlet fits precision-weighted linear mixed models
to pseudobulk, initialising weights from a Poisson model in which more cells and reads per sample mean higher
precision, then applies empirical Bayes moderation (Hoffman 2026, PMID 42778542) [dreamlet](../records.md#dreamlet). Its authors report that
the Poisson weights improved performance over the unweighted model, that it controlled the permuted-label false
positive rate (target 5%) where the muscat limma-voom path and GLMMs were inflated, and that it pseudobulked 2.2 million cells in 10
minutes with 20 GB (preprint, PMID 36993704). Plates, pools and processing batches can enter as random effects.

<a id="voombygroup"></a>**Unequal group variances.** voomByGroup fits a mean-variance trend per group and voomQWB one
weight per group; their authors show both improve error control and power when pseudobulk groups have unequal
variances, which they found common (You 2023, PMID 37147723) [voomByGroup and voomQWB](../records.md#voombygroup). Both need several replicates per group.

<a id="ruviii-pbps"></a>**Pseudosamples for removing plate effects, not for testing.** RUVIII-PBPS resamples cells within
biology-by-batch groups to build artificial pseudobulks used only to estimate unwanted-variation factors; it works
with one single-cell sample per group, reduced processing-cohort silhouette from 0.17 to 0.06 in a real dataset, and
controlled FDR where standard RUV could not be used (Prieto León 2025, PMID 41368194) [RUVIII with pseudobulk pseudosamples](../records.md#ruviii-pbps). It is the legitimate use of resampled cells: the DE test still
runs on real replicates.

<a id="mashr"></a>**Borrowing across conditions.** mashr learns covariance patterns of effects across conditions and
shrinks each condition's estimate toward them. On GTEx eQTLs in 44 tissues it called 47% of effects significant at
local false sign rate below 0.05, against 13% for condition-by-condition analysis (Urbut 2019, PMID 30478440)
[mashr](../records.md#mashr). A drug screen has the same shape (many drugs, shared pathways), and contrasts against one shared vehicle
control are handled through a reference condition in the package. No single-cell drug-screen benchmark was found.

<a id="dose-response-modelling"></a>**Doses as a trend.** sci-Plex modelled each gene as a function of dose by
generalized linear regression and found 6,238 genes with dose-dependent expression in at least one of three cell lines
(FDR below 5%) at a median of only 100 to 200 cells per condition (Srivatsan 2020, PMID 31806696) [sci-Plex](../records.md#sci-plex)
[Dose-response modelling across doses](../records.md#dose-response-modelling). General-purpose curve fitting is available in drc (Ritz 2015, PMID 26717316) and for
omics in DRomics (Larras 2018, PMID 30444611). Small effects agreed less well with bulk in sci-Plex.

<a id="trade"></a>**Effect-size summaries for whole perturbations.** TRADE models the distribution of true DE effects
from pseudobulk estimates and their standard errors. In five Perturb-seq screens, FDR-significant genes explained only
13% to 36% of each perturbation's estimated transcriptome-wide impact; a typical perturbation affected about 45 genes
(Nadig 2025, PMID 40259084) [TRADE](../records.md#trade). <a id="scdist"></a>scDist answers "did anything change" with a mixed model on
distances between condition means (Nicol 2024, PMID 39218971) [scDist](../records.md#scdist). The E-test of scPerturb is a permutation
test over cells (Peidli 2024, PMID 38279009); with one well per condition it tests whether two wells differ.

<a id="gsfa"></a>**Factor models across perturbations.** GSFA infers gene modules and each perturbation's effect on them;
in its authors' simulations its calls kept false discovery proportions well below 0.05 while edgeR and t-test calls
were inflated, with more power than t-test, edgeR-QLF and MAST (Zhou 2023, PMID 37770710) [GSFA](../records.md#gsfa).

<a id="decoupler"></a>**Program-level tests.** decoupler scores pathway and transcription-factor activity from footprint
gene sets (PROGENy, DoRothEA, CollecTRI); simple linear models and a consensus score best predicted perturbed
regulators (Badia-i-Mompel 2022, PMID 36699385) [decoupler / decoupleR](../records.md#decoupler). Footprints derived from bulk worked on scRNA-seq and
partly beat AUCell/SCENIC and metaVIPER, though PROGENy's AUROC fell from 0.724 to 0.636 as gene coverage dropped
(Holland 2020, PMID 32051003, same group). <a id="signature-scoring-evidence"></a>Scorer choice matters: Pagoda2 led
7 tools on 32 datasets (Zhang 2020, PMID 33209207); bulk-style scorers are biased by genes detected per cell
(Noureen 2022, PMID 35212622); and in a pseudobulk preprint benchmark, rank-based AUCell and UCell inverted the sign
of a pathway in 40% of simulated replicates under high competitor burden (Alakwaa 2026, PMID 42466400, preprint)
[signature-scoring-evidence](../records.md#signature-scoring-evidence).

## What the evidence says about deep models and imputation

<a id="ahlmann-eltze-2025"></a>**Prediction models.** Five foundation models plus GEARS and CPA were compared with
deliberately simple baselines; on 62 held-out double perturbations every model had prediction error substantially
higher than an additive baseline, and none beat a "no change" baseline at finding interactions (Ahlmann-Eltze 2025,
PMID 40759747) [ahlmann-eltze-2025](../records.md#ahlmann-eltze-2025). Two further studies found simple baselines ahead of deep models, a training-mean
baseline beating scGPT and scFoundation among them (Csendes 2025, PMID 40269681; Wong 2025, PMID 40407144). The finding is disputed: with calibrated
metrics and a positive-control baseline, deep models beat uninformative baselines across 14 datasets (Miller 2026,
PMID 42823510). A 13-method, 25-dataset comparison including two drug-response sets found models conservative, with
fine-tuned foundation models compressing variance and underestimating synergy, and no method generalising across
cell types (Li 2026, PMID 42715312).

<a id="cpa"></a>**CPA and chemCPA** decompose cells into a basal state plus perturbation and covariate embeddings with
learned dose-response curves, and predict unseen doses and combinations (Lotfollahi 2023, PMID 37154091; chemCPA,
Hetzel 2022, doi 10.48550/arXiv.2204.13545) [CPA and chemCPA](../records.md#cpa). The CPA paper itself assumes enough cells per condition to fit
the latent space, the opposite of the low-cell case. scGen, the earlier model from the same group, used latent vector
arithmetic (Lotfollahi 2019, PMID 31363220). <a id="mrvi"></a>MrVI adds a sample-aware latent space; on sci-Plex its
drug-dose distances agreed better with Connectivity Map than PCA- or scVI-based groupings (Boyeau 2025, PMID 41083897)
[MrVI](../records.md#mrvi). With one well per drug-dose, its "sample" is the well, so drug and well cannot be separated.
<a id="scvi-de"></a>scVI's Bayesian DE (Boyeau 2023, PMID 37192164) [scVI differential expression](../records.md#scvi-de) was no better than pseudobulk DESeq2 in
the nested benchmark (Hafner 2025, PMID 40794957).

<a id="imputation-de-evidence"></a>**Imputation.** Smoothing methods (MAGIC, knn-smooth, DCA) created many false-positive
DE genes and correlations; SAVER was least likely to, and the authors recommend testing on un-imputed data (Andrews
2018, PMID 30906525) [imputation-de-evidence](../records.md#imputation-de-evidence). In an 18-method evaluation, 13 of 16 methods raised overlap with bulk
DEGs when effects were large, but only 2 of 16 did when effects were small (Hou 2020, PMID 32854757). Drug screens at
low cell numbers are mostly in the small-effect regime.

## One culture per condition: what the p-value means

<a id="cell-subsample-pseudoreplicates"></a>Sample size in a cell experiment is the number of independent applications
of the treatment, not the number of cells measured (Lazic 2018, PMID 29617358; Vaux 2012, PMID 22421999; Blainey 2014,
PMID 25317452) [cell-subsample-pseudoreplicates](../records.md#cell-subsample-pseudoreplicates). In a survey of animal studies only 22% replicated the right unit and
46% pseudoreplicated (Lazic 2018, PMID 29617358). When one well's cells are split into subsets, any test compares the
two wells: a small p-value says the wells differ by more than cell sampling would explain, and any difference between the two
cultures, not only the drug, can produce that. Squair 2021 showed this directly (PMID 34584091). Effect sizes,
rankings and dose trends from such data remain useful, as long as they are reported as single-culture estimates.

## Hypotheses and open questions

<a id="pooled-variance-unreplicated-drugs"></a>**Pooled variance for unreplicated drugs (hypothesis).** In one linear
model over all wells, drugs with a single well can be tested against a residual variance estimated from replicated
wells, such as many vehicle wells [pooled-variance-unreplicated-drugs](../records.md#pooled-variance-unreplicated-drugs). The assumption that unreplicated drugs share
that variance is the one voomByGroup found often fails (You 2023, PMID 37147723). Untested in single-cell screens.

<a id="control-well-null"></a>**A well-to-well null (hypothesis).** Compute the same statistic for vehicle-vs-vehicle
well pairs and use its distribution as the threshold for drug-vs-vehicle calls [control-well-null](../records.md#control-well-null), generalising the
mock comparisons of Squair 2021 (PMID 34584091) and Junttila 2022 (PMID 35880426). It needs vehicle wells spread over
plates and positions.

Open questions: whether cell-count precision weights (dreamlet) or quality weights beat minimum-cells cut-offs in
screens with 1 to 3 wells per drug; whether mashr or dose models improve calibrated recall on a screen with held-out
replicate wells; and whether any perturbation model beats an additive baseline for unseen drugs at 50 to 200 cells
per condition.

<a id="hierarchicell"></a>**Power.** hierarchicell simulates within-sample correlation and shows that
calculators counting cells instead of independent units grossly overestimate power (Zimmerman 2021, PMID 33932993)
[hierarchicell](../records.md#hierarchicell); scPower models cost against samples, cells and depth and finds shallow sequencing of many cells
more powerful than deep sequencing of few (Schmid 2021, PMID 34785648) [scPower](../records.md#scpower); powsimR is an older simulation
framework (Vieth 2017, PMID 29036287). Design-side trade-offs (wells, plates, multiplexing) are covered in the [screen design chapter](04-screen-design.md),
for example [sci-Plex](../records.md#sci-plex) and [Tahoe-100M](../records.md#tahoe-100m).

## Ranked recommendations for low-cell multiplexed drug screens

| Rank | Do this | Expected gain (source) | Data needed | Main risk |
|---|---|---|---|---|
| 1 | Pseudobulk per well and cell type; test with edgeR, DESeq2 or limma; never use cell subsets of one well as replicates | Bulk-concordant calls; top six of 14 methods were pseudobulk (PMID 34584091) | Well identity per cell from demultiplexing ([demuxmix](../records.md#demuxmix), [HTODemux](../records.md#htodemux)) | No test at all for drugs with one well |
| 2 | Fit one model across all wells, plate as a covariate or random effect, with replicated vehicle wells | Residual degrees of freedom shared by every drug; batch covariates beat corrected data (PMID 36944632) | Several vehicle wells across plates | Unequal variances between drugs (PMID 37147723) |
| 3 | Keep small wells with weights (dreamlet, voomWithQualityWeights) rather than a hard cell floor | Weighted model outperformed unweighted (PMID 36993704, self-reported) | Cell counts per well | Weights do not model biological variance |
| 4 | Model dose as a trend | 6,238 dose-dependent genes at 100-200 cells per condition (PMID 31806696) | 3 or more doses per drug | Non-monotone responses |
| 5 | Test programs on pseudobulk contrasts (decoupler with PROGENy or CollecTRI) | Fewer, better-powered tests (PMID 36699385, 32051003) | Prior-knowledge gene sets | Gene-set choice; rank-based scorers can flip sign (PMID 42466400) |
| 6 | Shrink drug effects jointly (mashr) | 13% to 47% significant effects in eQTL data (PMID 30478440, self-reported) | Per-drug effects and standard errors | Untested on single-cell screens |
| 7 | Rank drugs by whole-transcriptome effect (TRADE, scDist) | Significant genes held 13-36% of total impact (PMID 40259084) | Replicate-level estimates | Bias for very small effects |
| 8 | Calibrate with vehicle-vs-vehicle wells | Real culture-to-culture null (hypothesis) | Many vehicle wells | Unvalidated |
| 9 | Use CPA, MrVI or other deep models for exploration only, against additive or linear baselines | None shown over baselines (PMID 40759747) | Many cells per condition | Confident predictions without uncertainty |
| 10 | Do not impute before testing | Avoids false positives (PMID 30906525) | None | Small effects erased (PMID 32854757) |

<!-- records:start -->

| Record | Kind | Tier | Side | Recovers / gain | Requires | Paper |
| --- | --- | --- | --- | --- | --- | --- |
| [Cell-subsample pseudoreplicates (one culture per condition)](#cell-subsample-pseudoreplicates) | evidence | `standard` | neutral | - | filtered-matrix | [paper](https://doi.org/10.1371/journal.pbio.2005282) 2018 |
| [decoupler / decoupleR (PROGENy, DoRothEA footprints)](#decoupler) | tool | `standard` | additive | One activity per pathway or regulator, pooling evidence from many weakly changed genes into a test with fewer comparisons / decoupleR benchmark: simple linear models and a consensus score best predicted perturbed regulators; Holland 2020: footprint gene sets worked on simulated and CRISPR scRNA-seq comparably to bulk and partly better than SCENIC/AUCell and metaVIPER; PROGENy AUROC fell from 0.724 to 0.636 as gene coverage dropped (self-reported) | filtered-matrix | [paper](https://doi.org/10.1093/bioadv/vbac016) 2022 |
| [Empirical Bayes moderation (limma, edgeR QL, DESeq2/apeglm)](#empirical-bayes-moderation) | method | `standard` | additive | Stable variance and effect estimates when each condition has very few replicates | replicates | [paper](https://doi.org/10.2202/1544-6115.1027) 2004 |
| [Junttila et al. 2022: multi-subject differential state benchmark](#junttila-2022) | evidence | `standard` | neutral | Pseudobulk methods had the highest average AUROC and clearly the best F1; naive methods had the highest sensitivity but many false positives, and adding latent-variable subject terms did not fix them (independent) | replicates | [paper](https://doi.org/10.1093/bib/bbac286) 2022 |
| [Minimum-cells rules for pseudobulk samples](#minimum-cells-rules) | method | `standard` | both | Lowering the floor and weighting by cell count keeps small wells as replicates instead of discarding them / Matched scRNA-seq and bulk of the same cells: about 2,000 cells per cluster were needed to recover most DEGs with modest bulk differences, while 50-100 cells recovered most DEGs with extremely small bulk p-values or abundance above a few hundred TPM (Liu 2023) (independent) | filtered-matrix | [paper](https://doi.org/10.1186/s12864-023-09487-y) 2023 |
| [Mixscape (and perturbation-response scores)](#mixscape) | tool | `standard` | additive | Effects diluted by non-responding cells; variation from replicate, cell cycle and stress removed from the signature / In the ECCITE-seq screen, 115 of 278 cells carrying an IFNGR2 gRNA appeared to escape perturbation; signatures substantially reduced replicate, cell-cycle and stress variation (self-reported) | multiple-conditions | [paper](https://doi.org/10.1038/s41588-021-00778-2) 2021 |
| [muscat](#muscat) | tool | `standard` | additive | Subpopulation-specific condition effects tested at the replicate level | filtered-matrix, replicates | [paper](https://doi.org/10.1038/s41467-020-19894-4) 2020 |
| [Pseudobulk differential expression](#pseudobulk-de) | method | `standard` | additive | Calibrated p-values and bulk-concordant DE calls, from samples of any cell count, using mature small-n statistics / All six top-ranked of 14 DE methods by concordance with matched bulk RNA-seq (AUCC) were pseudobulk methods across 18 gold-standard datasets (Squair 2021); pseudobulk had the highest average AUROC and best F1 among 18 methods (Junttila 2022) (independent) | filtered-matrix, replicates | [paper](https://doi.org/10.1038/s41576-023-00586-w) 2023 |
| [Squair et al. 2021: confronting false discoveries](#squair-2021) | evidence | `standard` | neutral | Single-cell methods called hundreds of DE genes between randomly assigned replicates with no perturbation; pseudobulk methods abolished these; random-cell pseudo-replicates brought the bias and the false DE genes back (independent) | replicates | [paper](https://doi.org/10.1038/s41467-021-25960-2) 2021 |
| [voomWithQualityWeights (limma sample weights)](#voom-quality-weights) | method | `standard` | additive | Power from samples that would otherwise be discarded as low quality / Down-weighting variable samples gave a more powerful analysis with fewer false discoveries than removing them or weighting equally, in simulations and RNA-seq data (self-reported) | replicates | [paper](https://doi.org/10.1093/nar/gkv412) 2015 |
| [CPA and chemCPA (compositional perturbation autoencoder)](#cpa) | tool | `benchmarked` | additive | Predicted responses for unmeasured drug-dose-combination conditions / Imputed 5,329 missing combinations (97.6% of all possibilities) in a combinatorial Perturb-seq screen and outperformed baseline models on unseen drug combinations in new A549 data (self-reported) | multiple-conditions, doses-or-time | [paper](https://doi.org/10.15252/msb.202211517) 2023 |
| [NEBULA](#nebula) | tool | `benchmarked` | additive | Cell-level information (including expressing fraction) while still accounting for within-sample correlation / NEBULA-HL and glmmTMB outperformed the other methods, including pseudobulk, in a 12-method simulation benchmark of multi-subject 10x data (Gagnon 2022); orders of magnitude faster than earlier GLMM tools (self-reported) (independent) | filtered-matrix, replicates | [paper](https://doi.org/10.1038/s42003-021-02146-6) 2021 |
| [scVI differential expression (lvm-DE)](#scvi-de) | tool | `benchmarked` | additive | Denoised, depth-corrected effect estimates for sparse genes / Outperformed state-of-the-art methods at estimating log fold change and detecting DE genes between cell subpopulations (self-reported) | filtered-matrix | [paper](https://doi.org/10.1073/pnas.2209124120) 2023 |
| [Ahlmann-Eltze et al. 2025: deep perturbation models vs linear baselines](#ahlmann-eltze-2025) | evidence | `published-unbenchmarked` | neutral | On 62 held-out double perturbations every deep model had prediction error substantially higher than the additive baseline, and none beat the 'no change' baseline at finding genetic interactions (independent) | - | [paper](https://doi.org/10.1038/s41592-025-02772-6) 2025 |
| [Dose-response modelling across doses](#dose-response-modelling) | method | `published-unbenchmarked` | additive | Power from doses that are individually underpowered; potency summaries (EC50-like) per drug / sci-Plex: generalized linear regression on dose found 6,238 genes with dose-dependent expression in at least one of three cell lines (FDR < 5%) at a median of 100-200 cells per condition (self-reported) | doses-or-time, multiple-conditions | [paper](https://doi.org/10.1371/journal.pone.0146021) 2015 |
| [dreamlet](#dreamlet) | tool | `published-unbenchmarked` | additive | Samples with few cells stay in the model at lower weight instead of being dropped; plates, pools and batches can enter as random effects / Poisson-initialised weights improved performance over the unweighted model; dreamlet controlled the permuted-label false positive rate (target 5%) across sample sizes where muscat limma-voom and glmer/MAST GLMMs were inflated; 2.2M cells from 1,000 donors x 12 cell types pseudobulked in 10 min with 20 GB (self-reported) | filtered-matrix, replicates | [paper](https://doi.org/10.1038/s41467-026-75680-8) 2026 |
| [Gene-set scoring benchmarks (cell-level and pseudobulk)](#signature-scoring-evidence) | evidence | `published-unbenchmarked` | neutral | - | filtered-matrix | [paper](https://doi.org/10.1016/j.csbj.2020.10.007) 2020 |
| [GSFA (guided sparse factor analysis)](#gsfa) | tool | `published-unbenchmarked` | additive | Gene-level perturbation effects detectable through shared modules when cells per perturbation are few (hundreds or fewer) / In simulations GSFA calls at LFSR < 0.05 kept false discovery proportions well below 0.05 in most settings while edgeR-QLF and t-test calls were inflated in count-based scenarios, with higher power than t-test, edgeR-QLF and MAST (self-reported) | multiple-conditions | [paper](https://doi.org/10.1038/s41592-023-02017-4) 2023 |
| [hierarchicell](#hierarchicell) | tool | `published-unbenchmarked` | neutral | - | replicates | [paper](https://doi.org/10.1186/s12864-021-07635-w) 2021 |
| [Imputation and smoothing before DE (Andrews & Hemberg 2018; Hou 2020)](#imputation-de-evidence) | evidence | `published-unbenchmarked` | neutral | Hou 2020 (18 methods): with large DE, 13 of 16 methods raised overlap with bulk DEGs; with small DE, only 2 of 16 did. Andrews & Hemberg: MAGIC, knn-smooth and DCA produced many false positives; SAVER was least likely to (independent) | filtered-matrix | [paper](https://doi.org/10.12688/f1000research.16613.2) 2018 |
| [mashr (multivariate adaptive shrinkage)](#mashr) | tool | `published-unbenchmarked` | additive | Effects in conditions that are underpowered alone but share effect patterns with related conditions (drugs of one class, doses of one drug) / GTEx eQTLs in 44 tissues: 47% of 707,036 top-SNP effects significant at lfsr < 0.05 with mash vs 13% for condition-by-condition ash and 39% for mash-bmalite (self-reported) | multiple-conditions | [paper](https://doi.org/10.1038/s41588-018-0268-8) 2019 |
| [MrVI (multi-resolution variational inference)](#mrvi) | tool | `published-unbenchmarked` | additive | Sample-level structure (which drugs or doses act alike) and local effects confined to cell subsets / On sci-Plex A549 (92 drugs x 4 doses as samples), MrVI sample distances agreed better with Connectivity Map drug similarity and placed doses of the same drug closer together than PCA- or scVI-based stratification (self-reported) | multiple-conditions | [paper](https://doi.org/10.1038/s41592-025-02808-x) 2025 |
| [Pseudobulk vs mixed models: Zimmerman 2021, Murphy & Skene 2022 and reply](#pseudobulk-vs-mixed-debate) | evidence | `published-unbenchmarked` | neutral | Murphy & Skene: at equal type 1 error, pseudobulk mean had sensitivity >0.9 while all other methods had <0.9 (hierarchicell simulation, 5-40 individuals, 50-500 cells); Zimmerman: pseudobulk conservative and underpowered vs GLMM/MAST_RE (independent) | replicates | [paper](https://doi.org/10.1038/s41467-021-21038-1) 2021 |
| [RUVIII with pseudobulk pseudosamples (RUVIII-PBPS)](#ruviii-pbps) | method | `published-unbenchmarked` | additive | Removal of plate or processing effects from pseudobulk DE when only one single-cell sample per group exists to define replicates for RUV / Processing-cohort ASW on 2 PCs fell from 0.17 to 0.06; FDR controlled where standard RUV could not be used; per-cell-type RUV2/RUVIII controlled FDR even under confounding (self-reported) | filtered-matrix | [paper](https://doi.org/10.1093/nargab/lqaf179) 2025 |
| [scDist](#scdist) | tool | `published-unbenchmarked` | additive | A replicate-aware answer to 'did anything change' when per-gene tests are underpowered / Outperformed current methods in simulated and real datasets even with limited sample sizes, with fewer false positives from individual and cohort variation (self-reported) | replicates | [paper](https://doi.org/10.1038/s41467-024-51649-3) 2024 |
| [TRADE (transcriptome-wide analysis of differential expression)](#trade) | tool | `published-unbenchmarked` | additive | A per-perturbation effect-size summary that remains estimable when few individual genes pass FDR / FDR-significant genes explained only 13-36% of estimated transcriptome-wide impact across five Perturb-seq screens (K562 genome-wide 36%, Jurkat essential 13%); a typical perturbation affected about 45 genes, essential genes over 500 (self-reported) | multiple-conditions, replicates | [paper](https://doi.org/10.1038/s41588-025-02169-3) 2025 |
| [voomByGroup and voomQWB](#voombygroup) | tool | `published-unbenchmarked` | additive | Power and error control lost when one high-variance group inflates (or a low-variance group deflates) the pooled variance / Better error control and power than voom, voomWithQualityWeights and other gold-standard methods when group variances differ (simulations and several pseudobulk datasets); common BCV ranged 0.338-0.495 across groups in a lung macrophage dataset (self-reported) | replicates | [paper](https://doi.org/10.1186/s13059-023-02949-2) 2023 |
| [Pooled residual variance for unreplicated drugs](#pooled-variance-unreplicated-drugs) | hypothesis | `hypothesis` | additive | A replicate-level test for unreplicated drugs without inventing replicates from cell subsets | multiple-conditions, replicates | - |
| [Well-to-well null from replicate control wells](#control-well-null) | hypothesis | `hypothesis` | additive | Calibrated calls in screens where most conditions have one well, using the null-comparison logic of the Squair 2021 and Junttila 2022 mock analyses | multiple-conditions | - |

<!-- records:end -->
