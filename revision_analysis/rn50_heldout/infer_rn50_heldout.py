#!/usr/bin/env python3
"""Inference of resnet50-res512-all (TorchXRayVision 1.4.0) on the pre-processed held-out NIH images.

Mirrors research/scripts/evaluate_id_models.py: xrv.datasets.normalize(img, maxval=255, reshape=True),
batch size 8, channels_last, default forward pass (sigmoid + operating-point normalization), outputs
clipped to [0, 1]. Resumable: one output file per archive part.

Denormal numbers are flushed to zero (torch.set_flush_denormal): most parameters of these weights are
denormal, which slows CPU inference by a factor of about 30 without changing the outputs.

Usage: infer_rn50_heldout.py <workdir> [<first part> <last part>]
"""
import json
import os
import sys
import time
import warnings

import numpy as np
import torch

warnings.filterwarnings("ignore")
torch.set_num_threads(int(os.environ.get("RN50_THREADS", "2")))
torch.set_flush_denormal(os.environ.get("RN50_FLUSH", "1") == "1")
import torchxrayvision as xrv  # noqa: E402

BATCH = 8


def main():
    work = sys.argv[1]
    first, last = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (1, 12)
    model = xrv.models.ResNet(weights="resnet50-res512-all", cache_dir=f"{work}/weights")
    model.eval()
    json.dump({"model": "resnet50-res512-all", "pathologies": list(model.pathologies), "torch": torch.__version__,
               "torchxrayvision": xrv.__version__, "batch_size": BATCH, "threads": torch.get_num_threads()},
              open(f"{work}/pred/run_env.json", "w"), indent=1)
    t_all, n_all = time.time(), 0
    for k in range(first, last + 1):
        part = f"part{k:03d}"
        out_path = f"{work}/pred/{part}.npy"
        if os.path.exists(out_path):
            continue
        waited = 0
        while not os.path.exists(f"{work}/pre/{part}.json"):
            time.sleep(15)
            waited += 15
            if waited > 3 * 3600:
                raise SystemExit(f"{part}: input never arrived")
        arr = np.load(f"{work}/pre/{part}.npy", mmap_mode="r")
        n = arr.shape[0]
        out = np.zeros((n, len(model.pathologies)), dtype=np.float32)
        start = 0
        ck = f"{work}/pred/{part}.partial.npz"
        if os.path.exists(ck):
            z = np.load(ck)
            start = int(z["done"])
            out[:start] = z["out"][:start]
        t0 = time.time()
        with torch.no_grad():
            for i in range(start, n, BATCH):
                j = min(i + BATCH, n)
                xb = np.stack([xrv.datasets.normalize(np.asarray(arr[r]), maxval=255, reshape=True) for r in range(i, j)])
                xb = torch.from_numpy(xb).float().to(memory_format=torch.channels_last)
                o = model(xb)
                out[i:j] = np.clip(o.detach().cpu().numpy().astype(np.float32), 0.0, 1.0)
                if (j // BATCH) % 40 == 0 or j == n:
                    np.savez(ck + ".tmp.npz", done=j, out=out)
                    os.replace(ck + ".tmp.npz", ck)
                    rate = (time.time() - t0) / max(1, j - start)
                    print(f"{part} {j}/{n}  {rate:.3f} s/img  elapsed {time.time() - t_all:.0f}s", flush=True)
        np.save(out_path + ".tmp.npy", out)
        os.replace(out_path + ".tmp.npy", out_path)
        os.remove(ck)
        n_all += n - start
        print(f"{part} done: {n} images", flush=True)
    print(f"ALL DONE in {time.time() - t_all:.0f}s", flush=True)


if __name__ == "__main__":
    main()
