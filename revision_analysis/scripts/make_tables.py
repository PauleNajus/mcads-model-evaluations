"""Generate LaTeX tables for the revised manuscript directly from the analysis outputs."""
import os
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import COMMON7, MODEL_KEYS, SHORT  # noqa: E402

OUT = os.environ.get("REV_OUT", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out"))
ood = json.load(open(f"{OUT}/ood_results.json"))
try:
    idr = json.load(open(f"{OUT}/id_results.json"))
except FileNotFoundError:
    idr = None

LAB = {"Pleural Effusion": "Pleural effusion"}


def f3(x):
    s = f"{x:.3f}"
    return s.replace("-", "$-$")


def f2(x):
    return f"{x:.2f}".replace("-", "$-$")


def _num(x):
    return ("$-$" if x < 0 else "") + f"{abs(x):.3f}"


def ci3(c):
    return f"{_num(c[0])}--{_num(c[1])}"


def sgn3(x):
    return ("+" if x >= 0 else "$-$") + f"{abs(x):.3f}"


def cid(c):
    a, b = c
    fa = ("$-$" if a < 0 else "") + f"{abs(a):.3f}"
    fb = ("$-$" if b < 0 else "") + f"{abs(b):.3f}"
    return f"{fa} to {fb}"


def pfmt(p):
    if p < 0.001:
        return "$<$0.001"
    if p >= 0.995:
        return "1.000" if p >= 0.9995 else f"{p:.3f}"
    return f"{p:.3f}"


def two(a, b):
    return f"\\twoline{{{a}}}{{({b})}}"


T = {}

# ---------------------------------------------------------------- Table: OOD macro
rows = []
for m in MODEL_KEYS:
    d = ood["discrimination"][m]
    c = ood["calibration_macro"][m]["default"]
    a = ood["all_mapped"][m]
    rows.append(" & ".join([
        SHORT[m],
        two(f3(d["macro7_auroc"]), ci3(d["macro7_auroc_ci"])),
        two(f3(d["macro5_auroc"]), ci3(d["macro5_auroc_ci"])),
        two(f3(d["macro7_auprc"]), ci3(d["macro7_auprc_ci"])),
        f3(c["brier"]), f3(c["ece"]),
        f"{f3(a['macro_excl'])} ({a['k_excl']})", f"{f3(a['macro_incl'])} ({a['k_incl']})",
    ]) + " \\\\")
T["ood_macro"] = "\n".join(rows)

# ---------------------------------------------------------------- Table: per-label AUROC
rows = []
for lab in COMMON7:
    pos = ood["discrimination"][MODEL_KEYS[0]]["per_label"][lab]["pos"]
    cells = [f"{LAB.get(lab, lab)} ({pos:,})"]
    for m in MODEL_KEYS:
        pl = ood["discrimination"][m]["per_label"][lab]
        cells.append(two(f3(pl["auroc"]), ci3(pl["auroc_ci"])))
    rows.append(" & ".join(cells) + " \\\\")
T["perlabel"] = "\n".join(rows)

# ---------------------------------------------------------------- Table: calibration across outputs
rows = []
for m in MODEL_KEYS:
    c = ood["calibration_macro"][m]
    rows.append(" & ".join([
        SHORT[m],
        f3(c["default"]["brier"]), f3(c["default"]["ece"]), f3(c["default"]["aece"]),
        f3(c["raw"]["brier"]), f3(c["raw"]["ece"]), f3(c["raw"]["aece"]), f2(c["raw"]["median_slope"]),
        f3(c["platt"]["brier"]), f3(c["platt"]["ece"]),
        f3(c["isotonic"]["brier"]), f3(c["isotonic"]["ece"]),
    ]) + " \\\\")
T["calib"] = "\n".join(rows)

# ---------------------------------------------------------------- Table: operating point
rows = []
for m in MODEL_KEYS:
    t = ood["threshold"][m]["macro"]
    flag = sum(ood["threshold"][m][l]["flag_rate"] for l in COMMON7) / 7
    v = ood["subgroups"]["view"]["results"][m]
    rows.append(" & ".join([
        SHORT[m], two(f3(t["sens"]), ci3(t["sens_ci"])), two(f3(t["spec"]), ci3(t["spec_ci"])),
        f"{100 * flag:.1f}",
        f3(v["AP"]["sens"]), f3(v["AP"]["spec"]), f3(v["PA"]["sens"]), f3(v["PA"]["spec"]),
    ]) + " \\\\")
T["oppoint"] = "\n".join(rows)

# ---------------------------------------------------------------- Subgroup tables with CIs
sub = ood["subgroups"]
dif = ood["subgroup_diffs"]
rows = []
for m in MODEL_KEYS:
    s = sub["sex"]["results"][m]
    v = sub["view"]["results"][m]
    d = dif[m]
    rows.append(" & ".join([
        SHORT[m], two(f3(s["F"]["macro"]), ci3(s["F"]["ci"])), two(f3(s["M"]["macro"]), ci3(s["M"]["ci"])),
        two(sgn3(d["male_minus_female"]), cid(d["male_minus_female_ci"])),
        two(f3(v["AP"]["macro"]), ci3(v["AP"]["ci"])), two(f3(v["PA"]["macro"]), ci3(v["PA"]["ci"])),
        two(sgn3(d["pa_minus_ap"]), cid(d["pa_minus_ap_ci"])),
    ]) + " \\\\")
T["sexview"] = "\n".join(rows)

rows = []
for m in MODEL_KEYS:
    r = sub["manufacturer"]["results"][m]
    vals = [r[c]["macro"] for c in ["1", "2", "3", "5", "6"]]
    rows.append(" & ".join([SHORT[m]] + [two(f3(r[c]["macro"]), ci3(r[c]["ci"])) for c in ["1", "2", "3", "5", "6"]]
                           + [f3(max(vals) - min(vals))]) + " \\\\")
T["manufacturer"] = "\n".join(rows)

AGES = ["0-4", "5-14", "15-24", "25-64", "65-84", ">=85"]
rows = []
for m in MODEL_KEYS:
    r = sub["age"]["results"][m]
    vals = [r[a]["macro"] for a in AGES]
    rows.append(" & ".join([SHORT[m]] + [two(f3(r[a]["macro"]), ci3(r[a]["ci"])) for a in AGES]
                           + [f3(max(vals) - min(vals))]) + " \\\\")
T["age"] = "\n".join(rows)

# ---------------------------------------------------------------- Stratified (main): age within PA + view within age
st = ood["stratified"]
rows = []
for m in MODEL_KEYS:
    a = st["age_within_PA"]["results"][m]
    v = st["view_within_age"]["results"][m]
    rows.append(" & ".join([SHORT[m]] + [two(f3(a[k]["macro"]), ci3(a[k]["ci"])) for k in ["15-24", "25-64", "65-84", ">=85"]]
                           + [two(f3(v[k]["macro"]), ci3(v[k]["ci"])) for k in ["child_AP", "child_PA", "adult_AP", "adult_PA"]]) + " \\\\")
T["stratified"] = "\n".join(rows)

# ---------------------------------------------------------------- Appendix: pairwise comparisons
p7 = {(r["a"], r["b"]): r for r in ood["pairwise_macro7"]}
p5 = {(r["a"], r["b"]): r for r in ood["pairwise_macro5"]}
rows = []
for k in p7:
    a, b = p7[k], p5[k]
    rows.append(" & ".join([f"{k[0]} vs. {k[1]}", sgn3(a["diff"]), cid(a["ci"]), pfmt(a["p_holm"]),
                            sgn3(b["diff"]), cid(b["ci"]), pfmt(b["p_holm"])]) + " \\\\")
T["pairwise"] = "\n".join(rows)

# ---------------------------------------------------------------- Appendix: per-label sensitivity / specificity
rows = []
for lab in COMMON7:
    cells = [LAB.get(lab, lab)]
    for m in MODEL_KEYS:
        t = ood["threshold"][m][lab]
        cells.append(f"\\twoline{{{t['sens']:.2f}}}{{{t['spec']:.2f}}}")
    rows.append(" & ".join(cells) + " \\\\")
T["sensspec_label"] = "\n".join(rows)

# ---------------------------------------------------------------- Appendix: macro sensitivity / specificity by subgroup
rows = []
groups = [("sex", "F", "Female"), ("sex", "M", "Male"), ("age", "0-4", "0--4 years"), ("age", "5-14", "5--14 years"),
          ("age", "15-24", "15--24 years"), ("age", "25-64", "25--64 years"), ("age", "65-84", "65--84 years"),
          ("age", ">=85", "$\\geq$85 years"), ("manufacturer", "1", "Code 1"), ("manufacturer", "2", "Code 2"),
          ("manufacturer", "3", "Code 3"), ("manufacturer", "5", "Code 5"), ("manufacturer", "6", "Code 6")]
for key, st_, name in groups:
    cells = [name]
    for m in MODEL_KEYS:
        r = sub[key]["results"][m][st_]
        cells.append(f"\\twoline{{{r['sens']:.2f}}}{{{r['spec']:.2f}}}")
    rows.append(" & ".join(cells) + " \\\\")
T["sensspec_sub"] = "\n".join(rows)

# ---------------------------------------------------------------- Appendix: positives per stratum
cnt = ood["subgroup_counts"]
rows = []
order = [("sex", "F", "Female"), ("sex", "M", "Male"), ("view", "AP", "AP"), ("view", "PA", "PA"),
         ("age", "0-4", "0--4 years"), ("age", "5-14", "5--14 years"), ("age", "15-24", "15--24 years"),
         ("age", "25-64", "25--64 years"), ("age", "65-84", "65--84 years"), ("age", ">=85", "$\\geq$85 years"),
         ("manufacturer", "1", "Code 1"), ("manufacturer", "2", "Code 2"), ("manufacturer", "3", "Code 3"),
         ("manufacturer", "5", "Code 5"), ("manufacturer", "6", "Code 6")]
for key, st_, name in order:
    c = cnt[key][st_]
    rows.append(" & ".join([name, f"{c['n']:,}"] + [f"{c[l]:,}" for l in COMMON7]) + " \\\\")
T["positives"] = "\n".join(rows)

# ---------------------------------------------------------------- Appendix: manufacturer within view + code 2 by age
rows = []
for m in MODEL_KEYS:
    ap = st["manufacturer_within_AP"]["results"][m]
    pa = st["manufacturer_within_PA"]["results"][m]
    rows.append(" & ".join([SHORT[m]] + [f3(ap[c]["macro"]) for c in ["1", "2", "3", "5", "6"]]
                           + [f3(pa[c]["macro"]) for c in ["1", "2", "3", "5", "6"]]) + " \\\\")
T["manu_within_view"] = "\n".join(rows)
rows = []
c2 = st["code2"]
for m in MODEL_KEYS:
    r = c2["results"][m]
    rows.append(" & ".join([SHORT[m]] + [two(f3(r[k]["macro"]), ci3(r[k]["ci"])) for k in ["code2_child", "code2_adult", "code2_all"]]) + " \\\\")
T["code2"] = "\n".join(rows)

# ---------------------------------------------------------------- Appendix: per-label calibration slope / intercept (raw)
rows = []
for lab in COMMON7:
    cells = [LAB.get(lab, lab)]
    for m in MODEL_KEYS:
        c = ood["calibration"][m][lab]["raw"]
        cells.append(f"\\twoline{{{f2(c['slope'])}}}{{{f2(c['intercept'])}}}")
    rows.append(" & ".join(cells) + " \\\\")
T["slopes"] = "\n".join(rows)

# ---------------------------------------------------------------- ID tables
if idr is not None:
    NIH14 = ["Atelectasis", "Cardiomegaly", "Consolidation", "Edema", "Effusion", "Emphysema", "Fibrosis", "Hernia",
             "Infiltration", "Mass", "Nodule", "Pleural_Thickening", "Pneumonia", "Pneumothorax"]
    SEVEN = ["Atelectasis", "Cardiomegaly", "Consolidation", "Edema", "Effusion", "Pneumonia", "Pneumothorax"]
    FIVE = ["Atelectasis", "Cardiomegaly", "Consolidation", "Effusion", "Pneumonia"]
    # held-out (20%) benchmarks distributed with TorchXRayVision (model definitions of version 1.4.0)
    PUB_ALL = dict(zip(NIH14, [0.76, 0.88, 0.77, 0.85, 0.85, 0.73, 0.72, 0.91, 0.68, 0.80, 0.69, 0.74, 0.71, 0.75]))
    PUB_RN = dict(zip(NIH14, [0.78, 0.90, 0.78, 0.89, 0.86, 0.88, 0.76, 0.92, 0.69, 0.82, 0.76, 0.76, 0.71, 0.84]))
    A, N, R = idr["DN121-All_heldout"], idr["DN121-NIH_heldout"], idr["RN50-All_heldout"]
    rows = []
    for l in NIH14:
        nm = l.replace("_", " ").capitalize() if l != "Pleural_Thickening" else "Pleural thickening"
        rows.append(" & ".join([nm, f"{A['per_label'][l]['pos']:,}", f3(A["per_label"][l]["auroc"]),
                                f"{PUB_ALL[l]:.2f}", f3(N["per_label"][l]["auroc"]),
                                f"{R['per_label'][l]['pos']:,}", f3(R["per_label"][l]["auroc"]), f"{PUB_RN[l]:.2f}"]) + " \\\\")
    rows.append("\\midrule")
    for key, name, labs in [("macro14", "Macro AUROC, 14 labels", NIH14), ("macro7", "Macro AUROC, 7 labels", SEVEN),
                            ("macro5", "Macro AUROC, 5 labels", FIVE)]:
        pa = sum(PUB_ALL[l] for l in labs) / len(labs)
        pr = sum(PUB_RN[l] for l in labs) / len(labs)
        rows.append(" & ".join([name, "--", two(f3(A[key]["auroc"]), ci3(A[key]["ci"])), f"{pa:.2f}",
                                two(f3(N[key]["auroc"]), ci3(N[key]["ci"])), "--",
                                two(f3(R[key]["auroc"]), ci3(R[key]["ci"])), f"{pr:.2f}"]) + " \\\\")
    for key, name in [("auprc", "Macro AUPRC, 14 labels"), ("brier", "Macro Brier score, 14 labels"),
                      ("ece", "Macro ECE, 14 labels")]:
        rows.append(" & ".join([name, "--", f3(A["macro14"][key]), "--", f3(N["macro14"][key]), "--",
                                f3(R["macro14"][key]), "--"]) + " \\\\")
    T["id"] = "\n".join(rows)

    io = idr["id_vs_ood"]
    pinfo = idr["partition_info"]
    size = {"DN121-All": f"{pinfo['dn_heldout_images']:,} ({pinfo['dn_heldout_patients']:,})",
            "DN121-NIH": f"{pinfo['dn_heldout_images']:,} ({pinfo['dn_heldout_patients']:,})",
            "RN50-All": f"{pinfo['rn_heldout_images']:,} ({pinfo['rn_heldout_patients']:,})"}
    mkey = {"DN121-All": "densenet121-res224-all", "DN121-NIH": "densenet121-res224-nih", "RN50-All": "resnet50-res512-all"}
    rows = []
    for key, mk in [("DN121-All", "DN121-All_heldout"), ("RN50-All", "RN50-All_heldout"), ("DN121-NIH", "DN121-NIH_heldout")]:
        x = io[key]
        rows.append(" & ".join([key, f3(x["id14"]),
                                two(f3(x["id7"]), ci3(idr[mk]["macro7"]["ci"])),
                                two(f3(x["ood7"]), ci3(ood["discrimination"][mkey[key]]["macro7_auroc_ci"])),
                                two(sgn3(x["d7"]), cid(x["d7_ci"])),
                                two(f3(x["id5"]), ci3(idr[mk]["macro5"]["ci"])),
                                two(sgn3(x["d5"]), cid(x["d5_ci"]))]) + " \\\\")
    T["idood"] = "\n".join(rows)

json.dump(T, open(f"{OUT}/tables.json", "w"), indent=1)
print("tables:", list(T))
