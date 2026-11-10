#!/usr/bin/env python3
"""Download NIH ChestX-ray14 image archives from the official NIH Clinical Center links and keep only
the images of the ResNet-50 held-out partition, pre-processed exactly as in the original evaluation
script (research/scripts/evaluate_id_models.py):

    PIL.Image.open(path).convert('L')  ->  resize((512, 512), BILINEAR) if needed  ->  uint8 array

Each archive is verified against the official MD5 checksum before use and deleted afterwards.

Usage: fetch_nih_heldout.py <workdir> <archive index 1-12> [<archive index> ...]
"""
import hashlib
import io
import json
import os
import subprocess
import sys
import tarfile
import time

import numpy as np
import PIL.Image

URLS = [
    "https://nihcc.box.com/shared/static/vfk49d74nhbxq3nqjg0900w5nvkorp5c.gz",
    "https://nihcc.box.com/shared/static/i28rlmbvmfjbl8p2n3ril0pptcmcu9d1.gz",
    "https://nihcc.box.com/shared/static/f1t00wrtdk94satdfb9olcolqx20z2jp.gz",
    "https://nihcc.box.com/shared/static/0aowwzs5lhjrceb3qp67ahp0rd1l1etg.gz",
    "https://nihcc.box.com/shared/static/v5e3goj22zr6h8tzualxfsqlqaygfbsn.gz",
    "https://nihcc.box.com/shared/static/asi7ikud9jwnkrnkj99jnpfkjdes7l6l.gz",
    "https://nihcc.box.com/shared/static/jn1b4mw4n6lnh74ovmcjb8y48h8xj07n.gz",
    "https://nihcc.box.com/shared/static/tvpxmn7qyrgl0w8wfh9kqfjskv6nmm1j.gz",
    "https://nihcc.box.com/shared/static/upyy3ml7qdumlgk2rfcvlb9k6gvqq2pj.gz",
    "https://nihcc.box.com/shared/static/l6nilvfa9cg3s28tqv1qc1olm3gnz54p.gz",
    "https://nihcc.box.com/shared/static/hhq8fkdgvcari67vfhs7ppg2w6ni4jze.gz",
    "https://nihcc.box.com/shared/static/ioqwiy20ihqwyr8pf4c24eazhh281pbu.gz",
]
MD5 = [
    "fe8ed0a6961412fddcbb3603c11b3698", "ab07a2d7cbe6f65ddd97b4ed7bde10bf",
    "2301d03bde4c246388bad3876965d574", "9f1b7f5aae01b13f4bc8e2c44a4b8ef6",
    "1861f3cd0ef7734df8104f2b0309023b", "456b53a8b351afd92a35bc41444c58c8",
    "1075121ea20a137b87f290d6a4a5965e", "b61f34cec3aa69f295fbb593cbd9d443",
    "442a3caa61ae9b64e61c561294d1e183", "09ec81c4c31e32858ad8cf965c494b74",
    "499aefc67207a5a97692424cf5dbeed5", "dc9fda1757c2de0032b63347a7d2895c",
]
SIZE = 512


def md5sum(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(work, k, need):
    part = f"part{k:03d}"
    done = f"{work}/pre/{part}.json"
    if os.path.exists(done):
        print(part, "already done", flush=True)
        return
    arch = f"{work}/dl/images_{k:03d}.tar.gz"
    t0 = time.time()
    for attempt in range(1, 4):
        for _ in range(8):
            r = subprocess.run(["curl", "-sS", "-L", "--fail", "-C", "-", "-o", arch, URLS[k - 1]])
            if r.returncode == 0:
                break
            time.sleep(10)
        got = md5sum(arch)
        if got == MD5[k - 1]:
            break
        print(part, "md5 mismatch on attempt", attempt, got, flush=True)
        os.remove(arch)
    else:
        raise SystemExit(f"{part}: could not download a verified archive")
    t1 = time.time()
    names, arrs, modes, sizes, total = [], [], {}, {}, 0
    with tarfile.open(arch, "r|gz") as tf:
        for m in tf:
            if not m.isfile():
                continue
            total += 1
            base = os.path.basename(m.name)
            if base not in need:
                continue
            im = PIL.Image.open(io.BytesIO(tf.extractfile(m).read()))
            modes[im.mode] = modes.get(im.mode, 0) + 1
            sizes[f"{im.size[0]}x{im.size[1]}"] = sizes.get(f"{im.size[0]}x{im.size[1]}", 0) + 1
            im = im.convert("L")
            if im.size[0] != SIZE or im.size[1] != SIZE:
                im = im.resize((SIZE, SIZE), PIL.Image.Resampling.BILINEAR)
            arrs.append(np.array(im))
            names.append(base)
    np.save(f"{work}/pre/{part}.tmp.npy", np.stack(arrs).astype(np.uint8))
    os.replace(f"{work}/pre/{part}.tmp.npy", f"{work}/pre/{part}.npy")
    json.dump({"archive": f"images_{k:03d}.tar.gz", "md5": got, "files_in_archive": total, "kept": len(names),
               "modes": modes, "sizes": sizes, "names": names, "pillow": PIL.__version__,
               "seconds_download": round(t1 - t0, 1), "seconds_extract": round(time.time() - t1, 1)},
              open(done + ".tmp", "w"))
    os.replace(done + ".tmp", done)
    os.remove(arch)
    print(part, "ok: archive files", total, "kept", len(names), modes, sizes,
          f"download {t1 - t0:.0f}s extract {time.time() - t1:.0f}s", flush=True)


if __name__ == "__main__":
    work = sys.argv[1]
    need = set(open(f"{work}/heldout_images.txt").read().split())
    for k in [int(a) for a in sys.argv[2:]]:
        fetch(work, k, need)
