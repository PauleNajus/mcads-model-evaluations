# Revision analyses for diagnostics-4648688

Code and aggregate outputs of the additional analyses performed during the first-round revision of
"Out-of-Distribution Generalization of Pre-Trained Multi-Label Chest X-Ray Classifiers: A Retrospective
External Validation of Seven Models" (Bundza and Trinkūnas, *Diagnostics*).

All analyses start from per-study predictions released in this repository:

* `results_ood/<model>/.../predictions_raw.csv` (BRAX, all seven models; original evaluation);
* `results_id/<model>/full_frontal_all/predictions_raw.csv` (NIH ChestX-ray14; original evaluation: complete
  collection for the two DenseNet-121 models and a 1,000-image label-stratified sample for `resnet50-res512-all`);
* `results_id/resnet50-res512-all/heldout_partition/predictions_raw.csv` (added in the revision: `resnet50-res512-all`
  on all 22,256 radiographs of the 6,161 patients held out from its training; see `rn50_heldout/`).

## Requirements

Python 3.13 with NumPy 2.5, SciPy 1.18, pandas 3.0, scikit-learn 1.9, statsmodels 0.15 and matplotlib 3.11.
PyTorch is not needed for the statistical analyses: `xrv_legacy_split.py` reproduces `torch.randperm` on the CPU
(MT19937, Fisher–Yates); the emulation was checked against PyTorch 2.5.1.

For the in-distribution analyses, a clone of the TorchXRayVision repository
(<https://github.com/mlmed/torchxrayvision>) is needed for three files:
`scripts/CrossReferenceWithNIH/rsnamatches.pkl` (RSNA–NIH image matches),
`torchxrayvision/data/google2019_nih-chest-xray-labels.csv.gz` (NIH images relabeled by Google) and
`torchxrayvision/data/Data_Entry_2017_v2020.csv.gz` (NIH metadata with the image identifiers).

## Running

Place this folder in the repository root (next to `results_id/` and `results_ood/`), or set the paths
with environment variables:

| Variable | Meaning | Default |
| --- | --- | --- |
| `EVAL_ROOT` | Folder that contains `results_id/` and `results_ood/` | parent of this folder |
| `XRV_REPO` | Clone of the TorchXRayVision repository | `torchxrayvision` |
| `REV_OUT` | Output folder for results and tables | `out/` |
| `REV_FIG` | Output folder for figures | `figures/` |
| `REV_B` | Number of bootstrap replicates in `run_id.py` | `2000` |

```bash
python scripts/run_ood.py      # BRAX analyses (about 7 min)
python scripts/run_id.py       # NIH ChestX-ray14 held-out partitions (about 17 min)
python scripts/make_tables.py  # LaTeX table bodies -> out/tables.json
python scripts/text_values.py  # in-distribution numbers quoted in the text -> out/text_values.json
python scripts/make_figures.py # Figures 2-5
```

All bootstrap analyses use 2000 patient-level cluster bootstrap replicates with seed 20261108.

## Held-out partitions

The TorchXRayVision weights were not trained on the official NIH training and test lists. `run_id.py`
reconstructs the partitions of the library's training scripts:

* DenseNet-121 weights: NIH restricted to the first PA radiograph of each patient, 50:50 `random_split` after
  `torch.manual_seed(0)`. Held-out partition: all 59,303 radiographs of the 16,371 patients not assigned to training.
* `resnet50-res512-all`: `GroupShuffleSplit(train_size=0.8, test_size=0.2, random_state=0)` on the patient
  identifier. Held-out partition: 22,256 radiographs of 6,161 patients. The benchmarks distributed with the library
  (`BENCHMARKS.md`, `scripts/model_calibrate.py`) are computed on the test portion of the same split.

## Inference of `resnet50-res512-all` on its held-out partition (`rn50_heldout/`)

| Script | Content |
| --- | --- |
| `make_list.py` | Lists the images of the held-out partition (`heldout_images.txt`, `heldout_meta.csv`) |
| `fetch_nih_heldout.py` | Downloads the 12 image archives from the NIH Clinical Center, verifies their MD5 checksums, and stores the held-out images after the preprocessing of the original evaluation (8-bit grayscale, bilinear resize to 512 × 512 pixels) |
| `infer_rn50_heldout.py` | Runs the model as in the original evaluation (TorchXRayVision 1.4.0, batch size 8, CPU, default forward pass) |
| `assemble_predictions.py` | Writes `predictions_raw.csv` and `run_info.json` and compares the new scores with the stored scores of the original 1,000-image sample |
| `flush_check.py` | Runs the same images with and without flushing denormal numbers and compares the scores |

```bash
python rn50_heldout/make_list.py <repository root>          # run inside the working folder
python rn50_heldout/fetch_nih_heldout.py <workdir> 1 2 3 4 5 6 7 8 9 10 11 12
python rn50_heldout/infer_rn50_heldout.py <workdir>
python rn50_heldout/assemble_predictions.py <workdir> <repository root>
```

Environment of the reported run: Python 3.13, PyTorch 2.15.0 (CPU), TorchXRayVision 1.4.0, Pillow 13.0, two CPU
cores. Denormal floating-point numbers were flushed to zero (`torch.set_flush_denormal(True)`) because most
parameters of these weights are denormal, which slows CPU inference by a factor of about 30; the setting did not
change the scores of a test batch (`flush_check.py`: identical scores). `run_info.json` records the archive checksums and the agreement with the
stored scores of the 186 radiographs that are also part of the original sample.

## Scripts

| Script | Content |
| --- | --- |
| `common.py` | Data loading, model order, inversion of the operating-point normalization, AUROC/AUPRC, ECE (equal-width and equal-mass), calibration intercept and slope, cluster bootstrap, Holm adjustment |
| `run_ood.py` | BRAX: macro AUROC/AUPRC (7 and 5 labels), paired model comparisons, all-mapped labels with and without exclusion, calibration of default and raw outputs, Platt and isotonic recalibration (5-fold patient-grouped cross-fitting), sensitivity and specificity at the default operating point, subgroup and stratified analyses |
| `run_id.py` | NIH ChestX-ray14: reconstruction of the training and held-out partitions, held-out ID metrics of the three models, training-versus-held-out permutation checks, RSNA/Google exclusion sensitivity analyses, evaluation on the library's benchmark partition and on the patients held out from the training of all three models, ID-to-OOD differences |
| `xrv_legacy_split.py` | Reproduction of the 50:50 `random_split` used for the DenseNet-121 weights |
| `load_rsnamatches.py` | Restricted unpickler for `rsnamatches.pkl` |
| `make_tables.py`, `make_figures.py`, `text_values.py` | Tables, Figures 2-5 and in-text numbers of the revised manuscript |
| `id_split_check.py`, `legacy_split_test.py`, `rn50_subset_check.py` | Exploratory checks of the partition reconstruction |

`xrv140_opthreshs.json` holds the operating thresholds of the seven weights in TorchXRayVision 1.4.0.

## Outputs (`out/`)

`ood_results.json`, `id_results.json` (all reported estimates and confidence intervals),
`ood_plotdata.json` (curves for the figures), `ood_macro7_boot.npy` and `ood_macro5_boot.npy`
(bootstrap replicates of the macro AUROC), `tables.json` (table bodies), `text_values.json`, and the run logs.
