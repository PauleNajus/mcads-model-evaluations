"""List the NIH ChestX-ray14 images in the held-out partition of resnet50-res512-all.

Partition: GroupShuffleSplit(train_size=0.8, test_size=0.2, random_state=0) on the patient ID
(as string, as in torchxrayvision.datasets.NIH_Dataset), all frontal (PA/AP) images of all patients.
"""
import json, os, sys
import numpy as np, pandas as pd
from sklearn.model_selection import GroupShuffleSplit
import torchxrayvision as xrv

ROOT = sys.argv[1]
dn = pd.read_csv(f"{ROOT}/results_id/densenet121-res224-all/full_frontal_all/predictions_raw.csv", dtype={"PatientID": str})
gss = GroupShuffleSplit(train_size=0.8, test_size=0.2, random_state=0)
_, te = next(gss.split(X=np.arange(len(dn)), groups=dn.PatientID.values.astype(str)))
test_pat = set(dn.PatientID.values[te].astype(int).tolist())

csvpath = os.path.join(os.path.dirname(xrv.__file__), "data", "Data_Entry_2017_v2020.csv.gz")
meta = pd.read_csv(csvpath)
meta = meta[meta["View Position"].isin(["PA", "AP"])]
# same split recomputed from the bundled metadata (independent of row order)
_, te2 = next(gss.split(X=np.arange(len(meta)), groups=meta["Patient ID"].astype(str).values))
test_pat2 = set(meta["Patient ID"].values[te2].astype(int).tolist())
print("patients", len(test_pat), len(test_pat2), "identical:", test_pat == test_pat2)
held = meta[meta["Patient ID"].isin(test_pat)].copy()
print("held-out images", len(held), "patients", held["Patient ID"].nunique(), "views", held["View Position"].value_counts().to_dict())
held.to_csv("heldout_meta.csv", index=False)
open("heldout_images.txt", "w").write("\n".join(held["Image Index"].tolist()) + "\n")
print(held.columns.tolist())
print(held.head(3).to_string())
