"""Numbers quoted in the manuscript text for the in-distribution (held-out) analyses.

Writes out/text_values.json (placeholders @@KEY@@ of the manuscript source) and prints a summary
that is used to check the wording of the text against the results.
"""
import json
import os
import sys

OUT = os.environ.get("REV_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out"))
SRC = OUT
idr = json.load(open(f"{SRC}/id_results.json"))
ood = json.load(open(f"{OUT}/ood_results.json"))

NIH14 = ["Atelectasis", "Cardiomegaly", "Consolidation", "Edema", "Effusion", "Emphysema", "Fibrosis", "Hernia",
         "Infiltration", "Mass", "Nodule", "Pleural_Thickening", "Pneumonia", "Pneumothorax"]
SEVEN = ["Atelectasis", "Cardiomegaly", "Consolidation", "Edema", "Effusion", "Pneumonia", "Pneumothorax"]
FIVE = ["Atelectasis", "Cardiomegaly", "Consolidation", "Effusion", "Pneumonia"]
PUB_ALL = dict(zip(NIH14, [0.76, 0.88, 0.77, 0.85, 0.85, 0.73, 0.72, 0.91, 0.68, 0.80, 0.69, 0.74, 0.71, 0.75]))
PUB_RN = dict(zip(NIH14, [0.78, 0.90, 0.78, 0.89, 0.86, 0.88, 0.76, 0.92, 0.69, 0.82, 0.76, 0.76, 0.71, 0.84]))


def f3(x):
    return f"{x:.3f}"


def ci(c):
    return f"{c[0]:.3f}--{c[1]:.3f}"


def pp(x):
    return f"{100 * x:.1f}"


def ppci(lo, hi):
    return f"{100 * lo:.1f}--{100 * hi:.1f}"


def pub_compare(res, pub):
    d = {l: res["per_label"][l]["auroc"] - pub[l] for l in NIH14}
    a = {l: abs(v) for l, v in d.items()}
    worst = max(a, key=a.get)
    return {"mad": sum(a.values()) / 14, "max": a[worst], "worst": worst, "worst_val": res["per_label"][worst]["auroc"],
            "worst_pub": pub[worst], "n01": sum(v <= 0.01 for v in a.values()), "n02": sum(v <= 0.02 for v in a.values()),
            "n_r2": sum(round(res["per_label"][l]["auroc"], 2) == round(pub[l], 2) for l in NIH14),
            "diffs": {l: round(v, 3) for l, v in d.items()}}


V, S = {}, {}
R, A, N = idr["RN50-All_heldout"], idr["DN121-All_heldout"], idr["DN121-NIH_heldout"]
P = idr["partition_info"]
io = idr["id_vs_ood"]

# --- RN50-All on its held-out partition
V["RN_ID14"], V["RN_ID14_CI"] = f3(R["macro14"]["auroc"]), ci(R["macro14"]["ci"])
V["RN_ID7"], V["RN_ID7_CI"] = f3(R["macro7"]["auroc"]), ci(R["macro7"]["ci"])
V["RN_ID5"], V["RN_ID5_CI"] = f3(R["macro5"]["auroc"]), ci(R["macro5"]["ci"])
c = pub_compare(R, PUB_RN)
S["RN50 vs published"] = c
V["RN_PUB_MAD"], V["RN_PUB_MAX"], V["RN_PUB_N01"], V["RN_PUB_N02"] = f3(c["mad"]), f3(c["max"]), str(c["n01"]), str(c["n02"])
for key in ["DN121-All_heldout", "DN121-All_benchmark", "DN121-All_full"]:
    if key in idr:
        S[f"{key} vs published"] = pub_compare(idr[key], PUB_ALL)
cb = pub_compare(idr["DN121-All_benchmark"], PUB_ALL)
V["ALL_BENCH_MAD"], V["ALL_BENCH_MAX"], V["ALL_BENCH_N01"] = f3(cb["mad"]), f3(cb["max"]), str(cb["n01"])
V["ALL_BENCH_ID14"], V["ALL_BENCH_ID14_CI"] = f3(idr["DN121-All_benchmark"]["macro14"]["auroc"]), ci(idr["DN121-All_benchmark"]["macro14"]["ci"])
V["NIH_BENCH_ID14"] = f3(idr["DN121-NIH_benchmark"]["macro14"]["auroc"])

# --- strict analysis
T = idr["RN50-All_heldout_strict"]
V["RN_STRICT_EXCL"] = f"{P['rn_strict_excluded_patients']:,}"
V["RN_STRICT_IMG"], V["RN_STRICT_PAT"] = f"{P['rn_strict_images']:,}", f"{P['rn_strict_patients']:,}"
V["RN_STRICT_AUC"], V["RN_STRICT_CI"] = f3(T["macro14"]["auroc"]), ci(T["macro14"]["ci"])
S["RN strict"] = {"macro14": T["macro14"]["auroc"], "macro7": T["macro7"]["auroc"], "macro5": T["macro5"]["auroc"],
                  "d7": io["RN50-All_strict"]["d7"], "d7_ci": io["RN50-All_strict"]["d7_ci"],
                  "d5": io["RN50-All_strict"]["d5"], "d5_ci": io["RN50-All_strict"]["d5_ci"]}

# --- reproduction of the stored outputs
rep = idr["rn50_reproduction"]
S["reproduction"] = rep
V["RN_REPRO_N"] = str(rep["n_overlap"])
m = rep["max_abs_diff"]
import math
e = math.ceil(math.log10(m)) if m > 0 else -9
V["RN_REPRO"] = "less than " + (f"{10.0 ** e:.{max(0, -e)}f}")

# --- ID versus OOD
dec = {}
for k in ["DN121-All", "RN50-All", "DN121-NIH"]:
    x = io[k]
    dec[k] = {"d7": -x["d7"], "d7_ci": (-x["d7_ci"][1], -x["d7_ci"][0]), "d5": -x["d5"], "d5_ci": (-x["d5_ci"][1], -x["d5_ci"][0]),
              "d14": x["id14"] - x["ood7"], "id7": x["id7"], "id5": x["id5"], "id14": x["id14"], "ood7": x["ood7"], "ood5": x["ood5"]}
S["declines"] = dec
V["RN_D7"], V["RN_D7_CI"] = pp(dec["RN50-All"]["d7"]), ppci(*dec["RN50-All"]["d7_ci"])
V["RN_D5"], V["RN_D5_CI"] = pp(dec["RN50-All"]["d5"]), ppci(*dec["RN50-All"]["d5_ci"])
V["RN_D14"] = pp(dec["RN50-All"]["d14"])
V["ALL_D7"], V["ALL_D7_CI"] = pp(dec["DN121-All"]["d7"]), ppci(*dec["DN121-All"]["d7_ci"])
V["NIH_D7"], V["NIH_D7_CI"] = pp(dec["DN121-NIH"]["d7"]), ppci(*dec["DN121-NIH"]["d7_ci"])
lo = min(d["d7"] for d in dec.values())
hi = max(d["d7"] for d in dec.values())
V["DECL_RANGE"] = f"{pp(lo)}--{pp(hi)}"
lo5 = min(d["d5"] for d in dec.values())
hi5 = max(d["d5"] for d in dec.values())
V["DECL_RANGE5"] = f"{pp(lo5)}--{pp(hi5)}"
V["RN_ID7_BRIER"], V["RN_ID7_ECE"] = f3(R["macro7"]["brier"]), f3(R["macro7"]["ece"])
S["RN id 7-label brier/ece"] = (R["macro7"]["brier"], R["macro7"]["ece"])
S["RN id 14-label auprc/brier/ece"] = (R["macro14"]["auprc"], R["macro14"]["brier"], R["macro14"]["ece"])
rn_ood = ood["calibration_macro"]["resnet50-res512-all"]["default"]
S["RN ood brier/ece"] = (rn_ood["brier"], rn_ood["ece"])
S["RN per-label ID -> OOD"] = {l: ood["discrimination"]["resnet50-res512-all"]["per_label"][
    {"Effusion": "Pleural Effusion"}.get(l, l)]["auroc"] - R["per_label"][l]["auroc"] for l in SEVEN}
_rd = S["RN per-label ID -> OOD"]
V["RN_EDEMA_D"], V["RN_PTX_D"] = f"{-100 * _rd['Edema']:.1f}", f"{-100 * _rd['Pneumothorax']:.1f}"
V["RN_OOD_ECE"] = f3(rn_ood["ece"])
d5 = idr["common_heldout"]["RN50-All_minus_DN121-All_macro5"]
V["CM_RN_ALL_D5"] = pp(d5["diff"])
V["CM_RN_ALL_CI5"] = f"{100 * d5['ci'][0]:.1f} to {100 * d5['ci'][1]:.1f}".replace("-", "$-$")


# --- patients held out from the training of all three models
C = idr["common_heldout"]
V["CM_IMG"], V["CM_PAT"] = f"{C['n_images']:,}", f"{C['n_patients']:,}"
for tag, k in [("RN", "RN50-All_common"), ("ALL", "DN121-All_common"), ("NIH", "DN121-NIH_common")]:
    V[f"CM_{tag}"], V[f"CM_{tag}_CI"] = f3(idr[k]["macro14"]["auroc"]), ci(idr[k]["macro14"]["ci"])
    V[f"CM_{tag}7"] = f3(idr[k]["macro7"]["auroc"])
d = C["RN50-All_minus_DN121-All_macro14"]
V["CM_RN_ALL_D"], V["CM_RN_ALL_CI"] = pp(d["diff"]), ppci(*d["ci"])
d = C["DN121-All_minus_DN121-NIH_macro14"]
V["CM_ALL_NIH_D"], V["CM_ALL_NIH_CI"] = pp(d["diff"]), ppci(*d["ci"])
S["common"] = C
V["BENCH_TRAIN_IMG"] = f"{C['dn_training_images_in_benchmark_partition']:,}"
V["BENCH_TRAIN_PCT"] = f"{100 * C['dn_training_images_in_benchmark_partition'] / C['benchmark_partition_images']:.1f}"

# --- partition composition
V["DN_AP_PCT"] = f"{100 * P['dn_heldout_ap_images'] / P['dn_heldout_images']:.1f}" if "dn_heldout_ap_images" in P else "??"
V["RN_AP_PCT"] = f"{100 * P['rn_heldout_ap_images'] / P['rn_heldout_images']:.1f}" if "rn_heldout_ap_images" in P else "??"
S["partition_info"] = P

json.dump(V, open(f"{SRC}/text_values.json", "w"), indent=1)
for k, v in S.items():
    print(f"== {k}\n   {json.dumps(v, default=float)}")
print("== values")
for k, v in V.items():
    print(f"   {k:18s} {v}")
