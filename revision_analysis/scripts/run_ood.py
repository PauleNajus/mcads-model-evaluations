"""Out-of-distribution (BRAX) analyses requested in the first-round review of diagnostics-4648688.

Outputs: out/ood_results.json (+ CSV tables)
"""
from __future__ import annotations

import os
import itertools
import json
import sys
import time

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (AGE_BANDS, COMMON7, FIVE, MODEL_KEYS, SHORT, RankPrep, calibration_intercept_slope,  # noqa
                    cluster_bootstrap_weights, ece_equal_mass, ece_equal_width, holm, inverse_opnorm, load_ood,
                    pct_ci, sens_spec, threshold_vector, _logit)

B = 2000
SEED = 20261108
CHUNK = 250
OUT = os.environ.get("REV_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out"))
t0 = time.time()


def log(*a):
    print(f"[{time.time() - t0:7.1f}s]", *a, flush=True)


meta, preds, maps = load_ood()
n = len(meta)
groups = meta.pid_code.values
Y = {lab: meta[lab].values.astype(int) for lab in COMMON7}
S = {m: {lab: preds[m][maps[m][lab]].values.astype(np.float64) for lab in COMMON7} for m in MODEL_KEYS}
T = {m: {lab: threshold_vector(m, maps[m][lab]) for lab in COMMON7} for m in MODEL_KEYS}
R = {m: {lab: inverse_opnorm(S[m][lab], T[m][lab]) for lab in COMMON7} for m in MODEL_KEYS}

log("bootstrap weights")
W = cluster_bootstrap_weights(groups, B, SEED)


def boot_metric(y, s, idx=None, kind="auc"):
    """Bootstrap distribution (B,) of AUROC or AP on rows idx (default all)."""
    if idx is not None:
        y, s = y[idx], s[idx]
    rp = RankPrep(y, s)
    out = np.empty(B)
    for a in range(0, B, CHUNK):
        Wc = W[a:a + CHUNK] if idx is None else W[a:a + CHUNK][:, idx]
        out[a:a + CHUNK] = rp.auroc(Wc) if kind == "auc" else rp.ap(Wc)
    return out


res: dict = {"B": B, "seed": SEED, "n_studies": int(n), "n_patients": int(groups.max() + 1)}

# ------------------------------------------------------------------------------------------------
# 1. Discrimination: per-label and macro AUROC / AUPRC with 2,000 cluster-bootstrap replicates
# ------------------------------------------------------------------------------------------------
log("per-label bootstrap")
auc_pt, ap_pt, auc_b, ap_b = {}, {}, {}, {}
for m in MODEL_KEYS:
    auc_pt[m], ap_pt[m], auc_b[m], ap_b[m] = {}, {}, {}, {}
    for lab in COMMON7:
        y, s = Y[lab], S[m][lab]
        auc_pt[m][lab] = roc_auc_score(y, s)
        ap_pt[m][lab] = average_precision_score(y, s)
        auc_b[m][lab] = boot_metric(y, s, kind="auc")
        ap_b[m][lab] = boot_metric(y, s, kind="ap")
    log("  ", SHORT[m])

disc = {}
macro7_b, macro5_b = {}, {}
for m in MODEL_KEYS:
    macro7_b[m] = np.mean([auc_b[m][l] for l in COMMON7], axis=0)
    macro5_b[m] = np.mean([auc_b[m][l] for l in FIVE], axis=0)
    ap7_b = np.mean([ap_b[m][l] for l in COMMON7], axis=0)
    disc[m] = {
        "per_label": {l: {"auroc": auc_pt[m][l], "auroc_ci": pct_ci(auc_b[m][l]),
                          "auprc": ap_pt[m][l], "auprc_ci": pct_ci(ap_b[m][l]),
                          "pos": int(Y[l].sum())} for l in COMMON7},
        "macro7_auroc": float(np.mean([auc_pt[m][l] for l in COMMON7])), "macro7_auroc_ci": pct_ci(macro7_b[m]),
        "macro5_auroc": float(np.mean([auc_pt[m][l] for l in FIVE])), "macro5_auroc_ci": pct_ci(macro5_b[m]),
        "macro7_auprc": float(np.mean([ap_pt[m][l] for l in COMMON7])), "macro7_auprc_ci": pct_ci(ap7_b),
    }
res["discrimination"] = disc
np.save(f"{OUT}/ood_macro7_boot.npy", np.vstack([macro7_b[m] for m in MODEL_KEYS]))
np.save(f"{OUT}/ood_macro5_boot.npy", np.vstack([macro5_b[m] for m in MODEL_KEYS]))

# ------------------------------------------------------------------------------------------------
# 2. Paired comparisons of macro AUROC (all 21 pairs), Holm adjustment
# ------------------------------------------------------------------------------------------------
from scipy.stats import norm  # noqa: E402


def pairwise(macro_pt, macro_b):
    rows = []
    for a, b in itertools.combinations(MODEL_KEYS, 2):
        d = macro_pt[a] - macro_pt[b]
        db = macro_b[a] - macro_b[b]
        se = float(np.std(db, ddof=1))
        z = d / se
        p = float(2 * norm.sf(abs(z)))
        p_perc = float(min(1.0, 2 * min((np.sum(db <= 0) + 1) / (B + 1), (np.sum(db >= 0) + 1) / (B + 1))))
        rows.append({"a": SHORT[a], "b": SHORT[b], "diff": d, "ci": pct_ci(db), "se": se, "z": z, "p": p,
                     "p_percentile": p_perc})
    adj = holm([r["p"] for r in rows])
    for r, q in zip(rows, adj):
        r["p_holm"] = float(q)
    return rows


res["pairwise_macro7"] = pairwise({m: disc[m]["macro7_auroc"] for m in MODEL_KEYS}, macro7_b)
res["pairwise_macro5"] = pairwise({m: disc[m]["macro5_auroc"] for m in MODEL_KEYS}, macro5_b)
log("pairwise done")

# ------------------------------------------------------------------------------------------------
# 3. All mapped labels: macro AUROC with and without the degenerate-pair exclusion
# ------------------------------------------------------------------------------------------------
allmap = {}
for m in MODEL_KEYS:
    vals = {}
    for lab, col in maps[m].items():
        y = meta[lab].values
        ok = np.isin(y, [0, 1])
        yy, ss = y[ok].astype(int), preds[m][col].values[ok]
        vals[lab] = {"auroc": float(roc_auc_score(yy, ss)), "var": float(np.var(ss)), "pos": int(yy.sum()),
                     "n": int(ok.sum())}
    degenerate = [l for l, v in vals.items() if v["var"] == 0 or abs(v["auroc"] - 0.5) <= 0.005]
    allmap[m] = {"labels": vals, "degenerate": degenerate,
                 "macro_excl": float(np.mean([v["auroc"] for l, v in vals.items() if l not in degenerate])),
                 "k_excl": len(vals) - len(degenerate),
                 "macro_incl": float(np.mean([v["auroc"] for v in vals.values()])), "k_incl": len(vals)}
res["all_mapped"] = allmap

# ------------------------------------------------------------------------------------------------
# 4. Calibration: default normalized scores, raw sigmoid outputs, and local recalibration
#    (Platt scaling and isotonic regression, 5-fold patient-grouped cross-fitting)
# ------------------------------------------------------------------------------------------------
log("calibration")
rng = np.random.default_rng(SEED)
upat = np.arange(groups.max() + 1)
fold_of_patient = np.empty(upat.size, dtype=int)
fold_of_patient[rng.permutation(upat.size)] = np.arange(upat.size) % 5
fold = fold_of_patient[groups]


def crossfit(y, raw):
    platt = np.empty(n)
    iso = np.empty(n)
    x = _logit(raw).reshape(-1, 1)
    for k in range(5):
        tr, te = fold != k, fold == k
        lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
        lr.fit(x[tr], y[tr])
        platt[te] = lr.predict_proba(x[te])[:, 1]
        ir = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        ir.fit(raw[tr], y[tr])
        iso[te] = ir.predict(raw[te])
    return platt, iso


def calib_metrics(y, p):
    a, b = calibration_intercept_slope(y, p)
    return {"brier": float(brier_score_loss(y, p)), "ece": ece_equal_width(y, p), "aece": ece_equal_mass(y, p),
            "intercept": a, "slope": b, "mean_score": float(np.mean(p)), "prevalence": float(np.mean(y))}


calib = {}
recal_scores = {}
for m in MODEL_KEYS:
    calib[m] = {}
    recal_scores[m] = {}
    for lab in COMMON7:
        y = Y[lab]
        platt, iso = crossfit(y, R[m][lab])
        recal_scores[m][lab] = (platt, iso)
        calib[m][lab] = {"default": calib_metrics(y, S[m][lab]), "raw": calib_metrics(y, R[m][lab]),
                         "platt": calib_metrics(y, platt), "isotonic": calib_metrics(y, iso),
                         "threshold": T[m][lab],
                         "auroc_platt": float(roc_auc_score(y, platt)),
                         "auroc_isotonic": float(roc_auc_score(y, iso))}
    log("  ", SHORT[m])
macro_cal = {}
for m in MODEL_KEYS:
    macro_cal[m] = {}
    for kind in ["default", "raw", "platt", "isotonic"]:
        macro_cal[m][kind] = {k: float(np.mean([calib[m][l][kind][k] for l in COMMON7]))
                              for k in ["brier", "ece", "aece", "intercept", "slope", "mean_score"]}
        macro_cal[m][kind]["median_slope"] = float(np.median([calib[m][l][kind]["slope"] for l in COMMON7]))
res["calibration"] = calib
res["calibration_macro"] = macro_cal

# ------------------------------------------------------------------------------------------------
# 5. Threshold metrics at the default operating point (normalized score >= 0.5)
# ------------------------------------------------------------------------------------------------
log("threshold metrics")
thr = {}
for m in MODEL_KEYS:
    thr[m] = {}
    se_b, sp_b = [], []
    for lab in COMMON7:
        y = Y[lab]
        pred = S[m][lab] >= 0.5
        se, sp = sens_spec(y, S[m][lab])
        # bootstrap CIs via weighted counts
        pos, neg = (y == 1), (y == 0)
        tp_w = (W[:, pos & pred]).sum(axis=1, dtype=np.int64)
        p_w = (W[:, pos]).sum(axis=1, dtype=np.int64)
        tn_w = (W[:, neg & ~pred]).sum(axis=1, dtype=np.int64)
        n_w = (W[:, neg]).sum(axis=1, dtype=np.int64)
        seb = tp_w / np.maximum(p_w, 1)
        spb = tn_w / np.maximum(n_w, 1)
        se_b.append(seb)
        sp_b.append(spb)
        thr[m][lab] = {"sens": se, "spec": sp, "sens_ci": pct_ci(seb), "spec_ci": pct_ci(spb),
                       "flag_rate": float(pred.mean()), "tp": int((pos & pred).sum()), "pos": int(pos.sum())}
    thr[m]["macro"] = {"sens": float(np.mean([thr[m][l]["sens"] for l in COMMON7])),
                       "spec": float(np.mean([thr[m][l]["spec"] for l in COMMON7])),
                       "sens_ci": pct_ci(np.mean(se_b, axis=0)), "spec_ci": pct_ci(np.mean(sp_b, axis=0))}
res["threshold"] = thr

# ------------------------------------------------------------------------------------------------
# 6. Subgroups (with CIs), threshold metrics by subgroup, positive counts per label
# ------------------------------------------------------------------------------------------------
log("subgroups")
SUBVARS = {
    "sex": ("PatientSex", ["F", "M"]),
    "view": ("ViewPosition", ["AP", "PA"]),
    "age": ("AgeBand", AGE_BANDS),
    "manufacturer": ("Manufacturer", [1, 2, 3, 5, 6]),
}


def labels_with_min_pos(masks, min_pos=10, candidates=COMMON7):
    return [l for l in candidates if all(Y[l][mk].sum() >= min_pos for mk in masks)]


def subgroup_block(masks: dict, labs):
    """masks: stratum -> boolean mask. Returns per model per stratum macro AUROC + CI + replicates."""
    out = {}
    reps = {}
    for m in MODEL_KEYS:
        out[m] = {}
        reps[m] = {}
        for st, mk in masks.items():
            idx = np.flatnonzero(mk)
            per = [roc_auc_score(Y[l][idx], S[m][l][idx]) for l in labs]
            bb = np.mean([boot_metric(Y[l], S[m][l], idx=idx) for l in labs], axis=0)
            reps[m][st] = bb
            out[m][st] = {"macro": float(np.mean(per)), "ci": pct_ci(bb),
                          "per_label": dict(zip(labs, map(float, per)))}
    return out, reps


sub = {}
sub_reps = {}
counts = {}
for key, (col, levels) in SUBVARS.items():
    masks = {str(v): (meta[col].values == v) for v in levels}
    labs = labels_with_min_pos(masks.values())
    o, rp = subgroup_block(masks, labs)
    sub[key] = {"labels": labs, "results": o}
    sub_reps[key] = rp
    counts[key] = {st: {"n": int(mk.sum()), **{l: int(Y[l][mk].sum()) for l in COMMON7}} for st, mk in masks.items()}
    # threshold metrics by subgroup (macro over the same labels)
    for m in MODEL_KEYS:
        for st, mk in masks.items():
            ses, sps = [], []
            for l in labs:
                se, sp = sens_spec(Y[l][mk], S[m][l][mk])
                ses.append(se)
                sps.append(sp)
            o[m][st]["sens"] = float(np.mean(ses))
            o[m][st]["spec"] = float(np.mean(sps))
    log("  ", key, labs)
# differences with CIs: male-female, PA-AP
diffs = {}
for m in MODEL_KEYS:
    d_sex = sub_reps["sex"][m]["M"] - sub_reps["sex"][m]["F"]
    d_view = sub_reps["view"][m]["PA"] - sub_reps["view"][m]["AP"]
    diffs[m] = {"male_minus_female": float(sub["sex"]["results"][m]["M"]["macro"] - sub["sex"]["results"][m]["F"]["macro"]),
                "male_minus_female_ci": pct_ci(d_sex),
                "pa_minus_ap": float(sub["view"]["results"][m]["PA"]["macro"] - sub["view"]["results"][m]["AP"]["macro"]),
                "pa_minus_ap_ci": pct_ci(d_view)}
res["subgroups"] = sub
res["subgroup_diffs"] = diffs
res["subgroup_counts"] = counts

# per-label sensitivity/specificity by subgroup (all seven labels) for the appendix
thr_sub = {}
for key, (col, levels) in SUBVARS.items():
    thr_sub[key] = {}
    for v in levels:
        mk = meta[col].values == v
        thr_sub[key][str(v)] = {}
        for m in MODEL_KEYS:
            thr_sub[key][str(v)][m] = {}
            for l in COMMON7:
                if Y[l][mk].sum() == 0:
                    continue
                se, sp = sens_spec(Y[l][mk], S[m][l][mk])
                thr_sub[key][str(v)][m][l] = {"sens": se, "spec": sp, "pos": int(Y[l][mk].sum())}
res["threshold_subgroups"] = thr_sub

# ------------------------------------------------------------------------------------------------
# 7. Stratified analyses
# ------------------------------------------------------------------------------------------------
log("stratified")
age = meta.AgeBand.values
view = meta.ViewPosition.values
manu = meta.Manufacturer.values
child = np.isin(age, ["0-4", "5-14"])
strat = {}
# 7a: age bands within PA radiographs
masks = {a: (view == "PA") & (age == a) for a in ["15-24", "25-64", "65-84", ">=85"]}
labs = labels_with_min_pos(masks.values())
o, _ = subgroup_block(masks, labs)
strat["age_within_PA"] = {"labels": labs, "results": o,
                          "n": {k: int(v.sum()) for k, v in masks.items()},
                          "pos": {k: {l: int(Y[l][v].sum()) for l in COMMON7} for k, v in masks.items()}}
log("  age within PA", labs)
# 7b: view within age groups (children 0-14, adults >=15)
masks = {"child_AP": child & (view == "AP"), "child_PA": child & (view == "PA"),
         "adult_AP": ~child & (view == "AP"), "adult_PA": ~child & (view == "PA")}
labs = labels_with_min_pos(masks.values())
o, rp = subgroup_block(masks, labs)
strat["view_within_age"] = {"labels": labs, "results": o,
                            "n": {k: int(v.sum()) for k, v in masks.items()},
                            "pos": {k: {l: int(Y[l][v].sum()) for l in COMMON7} for k, v in masks.items()},
                            "diff_child_PA_minus_AP": {m: {"d": o[m]["child_PA"]["macro"] - o[m]["child_AP"]["macro"],
                                                           "ci": pct_ci(rp[m]["child_PA"] - rp[m]["child_AP"])} for m in MODEL_KEYS},
                            "diff_adult_PA_minus_AP": {m: {"d": o[m]["adult_PA"]["macro"] - o[m]["adult_AP"]["macro"],
                                                           "ci": pct_ci(rp[m]["adult_PA"] - rp[m]["adult_AP"])} for m in MODEL_KEYS}}
log("  view within age", labs)
# 7c: manufacturer within AP and within PA
for vv in ["AP", "PA"]:
    codes = [1, 2, 3, 5, 6]
    masks = {str(c): (view == vv) & (manu == c) for c in codes}
    labs = labels_with_min_pos(masks.values())
    if len(labs) < 2:
        masks = {k: v for k, v in masks.items() if k != "2"}
        labs = labels_with_min_pos(masks.values())
    o, _ = subgroup_block(masks, labs)
    strat[f"manufacturer_within_{vv}"] = {"labels": labs, "results": o,
                                          "n": {k: int(v.sum()) for k, v in masks.items()},
                                          "pos": {k: {l: int(Y[l][v].sum()) for l in COMMON7} for k, v in masks.items()}}
    log(f"  manufacturer within {vv}", labs, list(masks))
# 7d: manufacturer code 2 by age group (children vs adults) and per label
c2 = manu == 2
masks = {"code2_child": c2 & child, "code2_adult": c2 & ~child, "code2_all": c2}
labs = labels_with_min_pos(masks.values())
o, _ = subgroup_block(masks, labs)
c2_detail = {"labels": labs, "results": o, "n": {k: int(v.sum()) for k, v in masks.items()},
             "pos": {k: {l: int(Y[l][v].sum()) for l in COMMON7} for k, v in masks.items()}}
# mean scores of positives vs negatives within code 2 by age group
ms = {}
for m in MODEL_KEYS:
    ms[m] = {}
    for l in labs:
        ms[m][l] = {}
        for g, mk in [("child", c2 & child), ("adult", c2 & ~child)]:
            ms[m][l][g] = {"pos_mean": float(S[m][l][mk & (Y[l] == 1)].mean()),
                           "neg_mean": float(S[m][l][mk & (Y[l] == 0)].mean()),
                           "npos": int((mk & (Y[l] == 1)).sum()), "nneg": int((mk & (Y[l] == 0)).sum())}
c2_detail["mean_scores"] = ms
# share of code-2 positives that are children, per label
c2_detail["child_share_of_pos"] = {l: float(Y[l][c2 & child].sum() / max(1, Y[l][c2].sum())) for l in COMMON7}
c2_detail["child_share_of_studies"] = float((c2 & child).sum() / c2.sum())
strat["code2"] = c2_detail
log("  code 2", labs)
res["stratified"] = strat

# ------------------------------------------------------------------------------------------------
# 8. Plot data: ROC curves, reliability diagrams (default, raw, isotonic)
# ------------------------------------------------------------------------------------------------
from sklearn.metrics import roc_curve  # noqa: E402

plot = {"roc": {}, "rel": {}}
for m in MODEL_KEYS:
    plot["roc"][m] = {}
    plot["rel"][m] = {}
    for l in COMMON7:
        f, t_, _ = roc_curve(Y[l], S[m][l])
        plot["roc"][m][l] = [f.tolist(), t_.tolist()]
        plot["rel"][m][l] = {}
        for kind, p in [("default", S[m][l]), ("raw", R[m][l]), ("isotonic", recal_scores[m][l][1]),
                        ("platt", recal_scores[m][l][0])]:
            bins = np.linspace(0, 1, 11)
            idx = np.clip(np.digitize(p, bins) - 1, 0, 9)
            rows = []
            for b in range(10):
                mk = idx == b
                if mk.any():
                    rows.append([float(p[mk].mean()), float(Y[l][mk].mean()), int(mk.sum())])
            plot["rel"][m][l][kind] = rows
json.dump(plot, open(f"{OUT}/ood_plotdata.json", "w"))

json.dump(res, open(f"{OUT}/ood_results.json", "w"), indent=1, default=float)
log("done")
