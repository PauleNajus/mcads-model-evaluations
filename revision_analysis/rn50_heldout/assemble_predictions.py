#!/usr/bin/env python3
"""Assemble the held-out predictions of resnet50-res512-all into predictions_raw.csv (same layout as the
files of the original evaluation, plus an ImageIndex column) and validate them against the stored
predictions of the original 1,000-image subset.

Usage: assemble_predictions.py <workdir> <evaluation repo root> [--partial]
"""
import json
import os
import sys

import numpy as np
import pandas as pd

NIH14 = ["Atelectasis", "Consolidation", "Infiltration", "Pneumothorax", "Edema", "Emphysema", "Fibrosis", "Effusion",
         "Pneumonia", "Pleural_Thickening", "Cardiomegaly", "Nodule", "Mass", "Hernia"]
EXTRA = ["Lung Lesion", "Fracture", "Lung Opacity", "Enlarged Cardiomediastinum"]


def main():
    work, root = sys.argv[1], sys.argv[2]
    partial = "--partial" in sys.argv
    env = json.load(open(f"{work}/pred/run_env.json"))
    assert env["pathologies"] == NIH14 + EXTRA, env["pathologies"]
    meta = pd.read_csv(f"{work}/heldout_meta.csv").set_index("Image Index")
    names, preds, info = [], [], []
    for k in range(1, 13):
        pj, pp = f"{work}/pre/part{k:03d}.json", f"{work}/pred/part{k:03d}.npy"
        if not (os.path.exists(pj) and os.path.exists(pp)):
            if partial:
                continue
            raise SystemExit(f"part{k:03d} missing")
        j = json.load(open(pj))
        p = np.load(pp)
        assert p.shape == (len(j["names"]), 18)
        names += j["names"]
        preds.append(p)
        info.append({k2: j[k2] for k2 in ("archive", "md5", "files_in_archive", "kept", "modes", "sizes", "pillow")})
    P = np.concatenate(preds)
    assert len(set(names)) == len(names)
    if not partial:
        assert set(names) == set(meta.index), (len(names), len(meta))
    m = meta.loc[names]
    df = pd.DataFrame({
        "ImageIndex": names,
        "PatientID": m["Patient ID"].astype(int).values,
        "PatientSex": m["Patient Gender"].values,
        "PatientAge": m["Patient Age"].astype(float).values,
        "ViewPosition": m["View Position"].values,
        "Manufacturer": "NIH_Dataset",
    })
    for lab in NIH14:
        df[lab] = m["Finding Labels"].str.contains(lab).astype(float).values
    for lab in EXTRA:
        df[lab] = np.nan
    for i, lab in enumerate(NIH14 + EXTRA):
        df["pred__" + lab] = P[:, i]
    df = df.sort_values("ImageIndex").reset_index(drop=True)
    print("images", len(df), "patients", df.PatientID.nunique(), "views", df.ViewPosition.value_counts().to_dict())
    print("prediction range", float(P.min()), float(P.max()), "NaN", int(np.isnan(P).sum()))

    # ---- validation 1: stored predictions of the original 1,000-image subset (same weights, same pipeline)
    old = pd.read_csv(f"{root}/results_id/resnet50-res512-all/full_frontal_all/predictions_raw.csv")
    pc = ["pred__" + lab for lab in NIH14 + EXTRA]
    lc = NIH14
    new_by_pat = {pid: g for pid, g in df.groupby("PatientID")}
    diffs, lab_ok, n_over = [], 0, 0
    for _, r in old.iterrows():
        g = new_by_pat.get(int(r.PatientID))
        if g is None:
            continue
        n_over += 1
        d = np.abs(g[pc].values.astype(np.float64) - r[pc].values.astype(np.float64)[None, :]).max(axis=1)
        j = int(np.argmin(d))
        diffs.append(float(d[j]))
        lab_ok += int((g[lc].values[j] == r[lc].values.astype(float)).all() and g.ViewPosition.values[j] == r.ViewPosition)
    diffs = np.array(diffs)
    print(f"overlap with the original 1,000-image subset: {n_over} images; max |difference| = {diffs.max():.3g}; "
          f"median = {np.median(diffs):.3g}; > 1e-4: {(diffs > 1e-4).sum()}; labels and view identical: {lab_ok}")

    # ---- validation 2: labels agree with those of the original evaluation (per patient, order-free)
    dn = pd.read_csv(f"{root}/results_id/densenet121-res224-all/full_frontal_all/predictions_raw.csv",
                     usecols=["PatientID", "ViewPosition"] + NIH14)
    dn = dn[dn.PatientID.isin(set(df.PatientID))]
    key_old = dn.groupby("PatientID")[NIH14].sum().sort_index()
    key_new = df.groupby("PatientID")[NIH14].sum().sort_index()
    same = bool((key_old.values == key_new.reindex(key_old.index).values).all()) if not partial else None
    n_old = int(len(dn))
    print("label counts per patient identical to the original evaluation:", same, "| images in original files:", n_old)
    if partial:
        return
    out = f"{root}/results_id/resnet50-res512-all/heldout_partition"
    os.makedirs(out, exist_ok=True)
    df.to_csv(f"{out}/predictions_raw.csv", index=False)
    json.dump({
        "model": "resnet50-res512-all", "img_size": 512, "batch_size": env["batch_size"], "device": "cpu",
        "n_images": int(len(df)), "n_patients": int(df.PatientID.nunique()),
        "partition": "held-out partition of the weights: GroupShuffleSplit(train_size=0.8, test_size=0.2, "
                     "random_state=0) on the patient ID, all frontal (PA/AP) images of the test patients",
        "image_source": "official NIH Clinical Center archives images_001-012.tar.gz (MD5 verified)",
        "archives": info,
        "preprocessing": "PIL convert('L'), bilinear resize to 512 x 512, xrv.datasets.normalize(maxval=255)",
        "torch": env["torch"], "torchxrayvision": env["torchxrayvision"],
        "validation": {"overlap_with_original_subset": int(n_over), "max_abs_difference": float(diffs.max()),
                       "labels_identical_per_patient": same},
    }, open(f"{out}/run_info.json", "w"), indent=2)
    print("written", out)


if __name__ == "__main__":
    main()
