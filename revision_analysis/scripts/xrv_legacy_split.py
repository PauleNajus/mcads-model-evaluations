"""Emulate torch.manual_seed(0); torch.utils.data.random_split(ds, [int(0.5n), n-int(0.5n)])
as used by the TorchXRayVision training script in 2019-2020 (DenseNet-121 weights), on the
NIH_Dataset defaults of that time (views=['PA'], unique_patients=True -> first PA image per patient,
rows ordered by Patient ID)."""
import numpy as np

def mt19937_raw(seed, n):
    rs = np.random.RandomState(seed)  # legacy seeding == init_genrand(seed)
    return rs._bit_generator.random_raw(n).astype(np.uint64)

def torch_randperm_cpu(n, seed=0):
    # Fisher-Yates as in TH/ATen randperm_cpu: z = random() % (n-i); swap(r[i], r[z+i])
    raw = mt19937_raw(seed, n - 1)
    r = np.arange(n, dtype=np.int64)
    for i in range(n - 1):
        z = int(raw[i] % np.uint64(n - i))
        r[i], r[z + i] = r[z + i], r[i]
    return r

def legacy_split_unique_pa(df):
    """df: NIH rows in Data_Entry_2017.csv order with columns PatientID (str/int), ViewPosition.
    Returns (train_pids, test_pids) for the unique-patient PA dataset (first PA image per patient)."""
    pa = df[df.ViewPosition == "PA"].copy()
    pa["pid_int"] = pa.PatientID.astype(int)
    first = pa.groupby("pid_int", sort=True).head(1)  # first PA row per patient in csv order
    first = first.sort_values("pid_int", kind="stable")
    n = len(first)
    train_size = int(0.5 * n)
    perm = torch_randperm_cpu(n, 0)
    tr_idx, te_idx = perm[:train_size], perm[train_size:]
    pids = first.pid_int.values
    return first.index.values[tr_idx], first.index.values[te_idx], pids[tr_idx], pids[te_idx]

if __name__ == "__main__":
    print("first mt19937(0) outputs:", mt19937_raw(0, 3))
