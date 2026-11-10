"""In-distribution (NIH ChestX-ray14) analyses for the revision of diagnostics-4648688.

Reconstructs the training/held-out partitions used by TorchXRayVision for the evaluated weights:
 * DenseNet-121 weights (2019-2020 training script): NIH_Dataset defaults of that time (PA views,
   one image per patient = first PA image), 50/50 torch.utils.data.random_split after torch.manual_seed(0).
 * ResNet-50 (res512-all; 2021 training script): GroupShuffleSplit(train 0.8, test 0.2, seed 0) on patient ID.
Held-out partition = all images of patients that were not in the training partition.
For ResNet-50, the held-out predictions come from results_id/resnet50-res512-all/heldout_partition
(see ../rn50_heldout/ for the inference code); the original 1,000-image subset is kept for comparison.
"""
from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, NIH14, RankPrep, cluster_bootstrap_weights, ece_equal_width, pct_ci  # noqa: E402
from load_rsnamatches import load as load_rsna  # noqa: E402
from xrv_legacy_split import legacy_split_unique_pa  # noqa: E402

B = int(os.environ.get("REV_B", "2000"))  # bootstrap replicates; 2000 in all reported analyses
XRV_REPO = os.environ.get("XRV_REPO", "torchxrayvision")  # clone of https://github.com/mlmed/torchxrayvision
SEED = 20261108
OUT = os.environ.get("REV_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out"))
COMMON7_NIH = ["Atelectasis", "Cardiomegaly", "Consolidation", "Edema", "Effusion", "Pneumonia", "Pneumothorax"]
FIVE_NIH = ["Atelectasis", "Cardiomegaly", "Consolidation", "Effusion", "Pneumonia"]
t0 = time.time()


def log(*a):
    print(f"[{time.time() - t0:7.1f}s]", *a, flush=True)


def load(m):
    return pd.read_csv(f"{ROOT}/results_id/{m}/full_frontal_all/predictions_raw.csv", dtype={"PatientID": str})


dn_all, dn_nih, rn = load("densenet121-res224-all"), load("densenet121-res224-nih"), load("resnet50-res512-all")
assert (dn_all.PatientID.values == dn_nih.PatientID.values).all()
pid_full = dn_all.PatientID.astype(int).values

# ---------------------------------------------------------------------------------------------
# Partitions
# ---------------------------------------------------------------------------------------------
tr_rows, te_rows, tr_pids, te_pids = legacy_split_unique_pa(dn_nih)
train_pat_dn = set(tr_pids.tolist())
heldout_dn = ~np.isin(pid_full, list(train_pat_dn))
log("DN121 legacy split: training patients", len(train_pat_dn), "held-out images", heldout_dn.sum(),
    "held-out patients", len(np.unique(pid_full[heldout_dn])))

# conservative exclusion for DN121-All: patients with any NIH image in the RSNA (Kaggle) or Google subsets
rsna = load_rsna(os.path.join(XRV_REPO, "scripts", "CrossReferenceWithNIH", "rsnamatches.pkl"))
rsna_imgs = [v["cxr_match"] for v in rsna.values() if float(v["mse"]) < 10]
google = pd.read_csv(os.path.join(XRV_REPO, "torchxrayvision", "data", "google2019_nih-chest-xray-labels.csv.gz"))
other_pat = set(int(x[:8]) for x in rsna_imgs) | set(google["Patient ID"].astype(int).tolist())
heldout_dn_strict = heldout_dn & ~np.isin(pid_full, list(other_pat))
log("DN121-All strict: excluded patients with RSNA/Google images:", len(other_pat), "remaining images",
    heldout_dn_strict.sum())

# GroupShuffleSplit for RN50-All (patient level)
gss = GroupShuffleSplit(train_size=0.8, test_size=0.2, random_state=0)
_, te_g = next(gss.split(X=np.arange(len(dn_all)), groups=dn_all.PatientID.values.astype(str)))
test_pat_rn = set(pid_full[te_g].tolist())
rn_pid = rn.PatientID.astype(int).values
rn_held = np.isin(rn_pid, list(test_pat_rn))
log("RN50 subset: held-out-partition images", rn_held.sum(), "of", len(rn))


# ---------------------------------------------------------------------------------------------
# Metrics with cluster bootstrap
# ---------------------------------------------------------------------------------------------
def evaluate(df, rows, seed_offset=0):
    d = df.loc[rows].reset_index(drop=True)
    grp = pd.factorize(d.PatientID)[0]
    Wl = cluster_bootstrap_weights(grp, B, SEED + seed_offset)
    per, boot = {}, {}
    for l in NIH14:
        y = d[l].values.astype(int)
        s = d["pred__" + l].values.astype(np.float64)
        rp = RankPrep(y, s)
        bb = np.concatenate([rp.auroc(Wl[a:a + 250]) for a in range(0, B, 250)])
        per[l] = {"auroc": float(roc_auc_score(y, s)), "ci": pct_ci(bb), "pos": int(y.sum()),
                  "auprc": float(average_precision_score(y, s)), "brier": float(brier_score_loss(y, s)),
                  "ece": ece_equal_width(y, s)}
        boot[l] = bb
    out = {"n_images": int(len(d)), "n_patients": int(grp.max() + 1), "per_label": per}
    for name, labs in [("macro14", NIH14), ("macro7", COMMON7_NIH), ("macro5", FIVE_NIH)]:
        bb = np.mean([boot[l] for l in labs], axis=0)
        out[name] = {"auroc": float(np.mean([per[l]["auroc"] for l in labs])), "ci": pct_ci(bb),
                     "auprc": float(np.mean([per[l]["auprc"] for l in labs])),
                     "brier": float(np.mean([per[l]["brier"] for l in labs])),
                     "ece": float(np.mean([per[l]["ece"] for l in labs]))}
        out[name + "_boot"] = bb
    return out


res = {}
allrows = np.arange(len(dn_all))
log("DN121-All held-out")
res["DN121-All_heldout"] = evaluate(dn_all, np.flatnonzero(heldout_dn), 1)
log("DN121-All held-out strict")
res["DN121-All_heldout_strict"] = evaluate(dn_all, np.flatnonzero(heldout_dn_strict), 2)
log("DN121-NIH held-out")
res["DN121-NIH_heldout"] = evaluate(dn_nih, np.flatnonzero(heldout_dn), 3)
log("DN121 full cohort")
res["DN121-All_full"] = evaluate(dn_all, allrows, 4)
res["DN121-NIH_full"] = evaluate(dn_nih, allrows, 5)
log("RN50 subset")
res["RN50-All_subset"] = evaluate(rn, np.arange(len(rn)), 6)
res["RN50-All_subset_heldout"] = evaluate(rn, np.flatnonzero(rn_held), 7)

# RN50-All on its complete held-out partition (inference added during the revision)
rn_h = pd.read_csv(f"{ROOT}/results_id/resnet50-res512-all/heldout_partition/predictions_raw.csv", dtype={"PatientID": str})
rn_h_pid = rn_h.PatientID.astype(int).values
assert set(rn_h_pid.tolist()) == test_pat_rn and len(rn_h) == int(np.isin(pid_full, list(test_pat_rn)).sum())
log("RN50 held-out partition:", len(rn_h), "images of", len(set(rn_h_pid.tolist())), "patients")
res["RN50-All_heldout"] = evaluate(rn_h, np.arange(len(rn_h)), 8)
# conservative exclusion for RN50-All: patients with any NIH image matched to the RSNA challenge data
rsna_pat = set(int(x[:8]) for x in rsna_imgs)
rn_h_strict = ~np.isin(rn_h_pid, list(rsna_pat))
log("RN50 strict: excluded patients", len(rsna_pat & set(rn_h_pid.tolist())), "remaining images", rn_h_strict.sum())
res["RN50-All_heldout_strict"] = evaluate(rn_h, np.flatnonzero(rn_h_strict), 9)
# agreement of the new outputs with the stored outputs of the original 1,000-image subset
pc = ["pred__" + l for l in NIH14]
by_pat = {p: g[pc].values.astype(np.float64) for p, g in rn_h.groupby(rn_h_pid)}
dmax = [float(np.abs(by_pat[p] - r[None, :]).max(axis=1).min())
        for p, r in zip(rn_pid[rn_held], rn.loc[rn_held, pc].values.astype(np.float64))]
res["rn50_reproduction"] = {"n_overlap": int(len(dmax)), "max_abs_diff": float(np.max(dmax))}
log("RN50 reproduction of stored subset outputs:", res["rn50_reproduction"])

# ---------------------------------------------------------------------------------------------
# Library benchmark partition and patients held out from the training of all three models
# ---------------------------------------------------------------------------------------------
# The benchmarks distributed with TorchXRayVision (BENCHMARKS.md, scripts/model_calibrate.py) are computed on the
# test portion of the same GroupShuffleSplit, i.e., on the held-out partition of RN50-All.
# The rows of the stored DenseNet-121 files follow the images sorted by image index; this is verified with the
# patient, view position and labels of every row before the image identifiers are attached.
meta = pd.read_csv(os.path.join(XRV_REPO, "torchxrayvision", "data", "Data_Entry_2017_v2020.csv.gz"))
meta = meta[meta["View Position"].isin(["PA", "AP"])].sort_values("Image Index").reset_index(drop=True)
assert len(meta) == len(dn_all) and (meta["Patient ID"].values == pid_full).all()
assert (meta["View Position"].values == dn_all.ViewPosition.values).all()
for l in NIH14:
    assert (meta["Finding Labels"].str.contains(l).values == (dn_all[l].values == 1)).all(), l
img_full = meta["Image Index"].values

bench_rows = np.flatnonzero(np.isin(pid_full, list(test_pat_rn)))
assert len(bench_rows) == len(rn_h) and set(img_full[bench_rows]) == set(rn_h.ImageIndex)
log("DN121 on the library benchmark partition")
res["DN121-All_benchmark"] = evaluate(dn_all, bench_rows, 10)
res["DN121-NIH_benchmark"] = evaluate(dn_nih, bench_rows, 11)
n_tr_in_bench = int(np.isin(bench_rows, tr_rows).sum())

common_rows = np.flatnonzero(heldout_dn & np.isin(pid_full, list(test_pat_rn)))
rn_c = rn_h.set_index("ImageIndex").loc[img_full[common_rows]].reset_index()
assert (rn_c.PatientID.astype(int).values == pid_full[common_rows]).all()
for l in NIH14:
    assert (rn_c[l].values == dn_all[l].values[common_rows]).all(), l
log("common held-out patients:", len(common_rows), "images of", len(np.unique(pid_full[common_rows])), "patients")
# identical rows, patients and seed -> identical bootstrap replicates for the three models (paired comparison)
res["DN121-All_common"] = evaluate(dn_all, common_rows, 12)
res["DN121-NIH_common"] = evaluate(dn_nih, common_rows, 12)
res["RN50-All_common"] = evaluate(rn_c, np.arange(len(rn_c)), 12)
cm = {"n_images": int(len(common_rows)), "n_patients": int(len(np.unique(pid_full[common_rows]))),
      "dn_training_images_in_benchmark_partition": n_tr_in_bench, "benchmark_partition_images": int(len(bench_rows))}
for a, b in [("RN50-All", "DN121-All"), ("RN50-All", "DN121-NIH"), ("DN121-All", "DN121-NIH")]:
    for name in ["macro14", "macro7", "macro5"]:
        d = res[a + "_common"][name + "_boot"] - res[b + "_common"][name + "_boot"]
        est = res[a + "_common"][name]["auroc"] - res[b + "_common"][name]["auroc"]
        cm[f"{a}_minus_{b}_{name}"] = {"diff": float(est), "ci": pct_ci(d)}
res["common_heldout"] = cm
log("common held-out:", {k: v for k, v in cm.items() if "macro14" in k})


# ---------------------------------------------------------------------------------------------
# Memorization checks (training vs held-out partition, null from random patient-level splits)
# ---------------------------------------------------------------------------------------------
def macro(d, rows, labs=NIH14):
    v = []
    for l in labs:
        y = d[l].values[rows]
        if 0 < y.sum() < len(y):
            v.append(roc_auc_score(y, d["pred__" + l].values[rows]))
    return float(np.mean(v))


rng = np.random.default_rng(SEED)
mem = {}
first_rows = np.concatenate([tr_rows, te_rows])
for name, d in [("DN121-NIH", dn_nih), ("DN121-All", dn_all)]:
    gap = macro(d, tr_rows) - macro(d, te_rows)
    null = []
    for _ in range(500):
        p = rng.permutation(first_rows)
        null.append(macro(d, p[:len(tr_rows)]) - macro(d, p[len(tr_rows):]))
    null = np.array(null)
    mem[name] = {"train_macro": macro(d, tr_rows), "heldout_macro": macro(d, te_rows), "gap": gap,
                 "null_lo": float(np.percentile(null, 2.5)), "null_hi": float(np.percentile(null, 97.5)),
                 "p_one_sided": float((np.sum(null >= gap) + 1) / (len(null) + 1)), "n_each": int(len(tr_rows))}
    log("memorization", name, mem[name])
# RN50 within its 1,000-image subset
up = np.unique(rn_pid)
ntest = len(set(rn_pid) & test_pat_rn)
gap = macro(rn, np.flatnonzero(~rn_held)) - macro(rn, np.flatnonzero(rn_held))
null = []
for _ in range(500):
    sel = rng.choice(up, size=ntest, replace=False)
    mk = np.isin(rn_pid, sel)
    null.append(macro(rn, np.flatnonzero(~mk)) - macro(rn, np.flatnonzero(mk)))
null = np.array(null)
mem["RN50-All"] = {"train_macro": macro(rn, np.flatnonzero(~rn_held)), "heldout_macro": macro(rn, np.flatnonzero(rn_held)),
                   "gap": gap, "null_lo": float(np.percentile(null, 2.5)), "null_hi": float(np.percentile(null, 97.5)),
                   "p_one_sided": float((np.sum(null >= gap) + 1) / (len(null) + 1)),
                   "n_train": int((~rn_held).sum()), "n_heldout": int(rn_held.sum())}
log("memorization RN50", mem["RN50-All"])
res["memorization"] = mem
res["partition_info"] = {
    "dn_unique_pa_patients": int(len(tr_rows) + len(te_rows)), "dn_training_patients": int(len(train_pat_dn)),
    "dn_heldout_images": int(heldout_dn.sum()), "dn_heldout_patients": int(len(np.unique(pid_full[heldout_dn]))),
    "dn_strict_excluded_patients": int(len(other_pat & set(pid_full[heldout_dn].tolist()))),
    "dn_strict_images": int(heldout_dn_strict.sum()),
    "dn_strict_patients": int(len(np.unique(pid_full[heldout_dn_strict]))),
    "rn_test_patients": int(len(test_pat_rn)), "rn_test_images_full": int(np.isin(pid_full, list(test_pat_rn)).sum()),
    "rn_subset_heldout_images": int(rn_held.sum()),
    "rn_heldout_images": int(len(rn_h)), "rn_heldout_patients": int(len(set(rn_h_pid.tolist()))),
    "rn_strict_excluded_patients": int(len(rsna_pat & set(rn_h_pid.tolist()))),
    "rn_strict_images": int(rn_h_strict.sum()),
    "rn_strict_patients": int(len(set(rn_h_pid[rn_h_strict].tolist()))),
    "rsna_matched_images": len(rsna_imgs), "google_images": int(len(google)),
    "dn_heldout_ap_images": int((dn_all.ViewPosition.values[heldout_dn] == "AP").sum()),
    "rn_heldout_ap_images": int((rn_h.ViewPosition.values == "AP").sum()),
    "rn_heldout_images_of_dn_training_patients": int(np.isin(rn_h_pid, list(train_pat_dn)).sum()),
}

# ---------------------------------------------------------------------------------------------
# ID versus OOD (independent bootstrap replicates of the two cohorts)
# ---------------------------------------------------------------------------------------------
ood7 = np.load(f"{OUT}/ood_macro7_boot.npy")[:, :B]
ood5 = np.load(f"{OUT}/ood_macro5_boot.npy")[:, :B]
ood = json.load(open(f"{OUT}/ood_results.json"))
order = ["densenet121-res224-pc", "densenet121-res224-all", "resnet50-res512-all", "densenet121-res224-chex",
         "densenet121-res224-mimic_ch", "densenet121-res224-nih", "densenet121-res224-mimic_nb"]
idood = {}
for key, mkey, idkey in [("DN121-All", "densenet121-res224-all", "DN121-All_heldout"),
                         ("DN121-NIH", "densenet121-res224-nih", "DN121-NIH_heldout"),
                         ("RN50-All", "resnet50-res512-all", "RN50-All_heldout"),
                         ("RN50-All_subset", "resnet50-res512-all", "RN50-All_subset"),
                         ("RN50-All_strict", "resnet50-res512-all", "RN50-All_heldout_strict"),
                         ("DN121-All_full", "densenet121-res224-all", "DN121-All_full"),
                         ("DN121-NIH_full", "densenet121-res224-nih", "DN121-NIH_full"),
                         ("DN121-All_strict", "densenet121-res224-all", "DN121-All_heldout_strict")]:
    i = order.index(mkey)
    o7, o5 = ood["discrimination"][mkey]["macro7_auroc"], ood["discrimination"][mkey]["macro5_auroc"]
    i7, i5 = res[idkey]["macro7"]["auroc"], res[idkey]["macro5"]["auroc"]
    idood[key] = {"id7": i7, "ood7": o7, "d7": o7 - i7, "d7_ci": pct_ci(ood7[i] - res[idkey]["macro7_boot"]),
                  "id5": i5, "ood5": o5, "d5": o5 - i5, "d5_ci": pct_ci(ood5[i] - res[idkey]["macro5_boot"]),
                  "id14": res[idkey]["macro14"]["auroc"]}
res["id_vs_ood"] = idood

for k in list(res):
    if isinstance(res[k], dict):
        for kk in [x for x in res[k] if x.endswith("_boot")]:
            del res[k][kk]
json.dump(res, open(f"{OUT}/id_results.json", "w"), indent=1, default=float)
log("done")
