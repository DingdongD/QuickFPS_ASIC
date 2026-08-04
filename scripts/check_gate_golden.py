#!/usr/bin/env python3
import argparse
import importlib.util
import json
import struct
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]


def bits_f32(x):
    return np.float32(struct.unpack(">f", struct.pack(">I", x & 0xFFFFFFFF))[0])


def load_qg():
    spec = importlib.util.spec_from_file_location("qg", ROOT / "scripts" / "run_quickfps_golden.py")
    qg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qg)
    return qg


def check_pe(log):
    qg = load_qg()
    _, cases, center = qg.gen_pe_tb()
    mx, my, mz = center
    got = {}
    for line in log.read_text(errors="ignore").splitlines():
        if line.startswith("PEOUT"):
            _, idx, dist = line.split()
            got[int(idx)] = qg.bits_f32(int(dist, 16))
    mismatches = 0
    max_abs = 0.0
    for i, x, y, z, in_dist in cases:
        d = np.float32(
            np.float32((x - mx) * (x - mx))
            + np.float32((y - my) * (y - my))
            + np.float32((z - mz) * (z - mz))
        )
        ref = np.float32(min(np.float32(in_dist), d))
        if i not in got:
            mismatches += 1
            continue
        err = float(abs(got[i] - ref))
        max_abs = max(max_abs, err)
        if err > 5e-2:
            mismatches += 1
    return {"pass": mismatches == 0, "cases": len(cases), "observed": len(got), "mismatches": mismatches, "max_abs": max_abs}


def check_bucket_cd(log):
    qg = load_qg()
    _, cases = qg.gen_bucket_cd_tb()
    got = {}
    for line in log.read_text(errors="ignore").splitlines():
        if line.startswith("CDOUT"):
            _, idx, dlb, dist = line.split()
            got[int(idx)] = (qg.bits_f32(int(dlb, 16)), qg.bits_f32(int(dist, 16)))
    mismatches = 0
    max_abs_dlb = 0.0
    max_abs_d = 0.0
    for c in cases:
        i, qx, qy, qz, minx, miny, minz, maxx, maxy, maxz, fpx, fpy, fpz = c
        gapx = max(minx - qx, 0.0, qx - maxx)
        gapy = max(miny - qy, 0.0, qy - maxy)
        gapz = max(minz - qz, 0.0, qz - maxz)
        dlb_ref = np.float32(np.float32(gapx * gapx) + np.float32(gapy * gapy) + np.float32(gapz * gapz))
        d_ref = np.float32(
            np.float32((qx - fpx) * (qx - fpx))
            + np.float32((qy - fpy) * (qy - fpy))
            + np.float32((qz - fpz) * (qz - fpz))
        )
        if i not in got:
            mismatches += 1
            continue
        dlb_got, d_got = got[i]
        edlb = float(abs(dlb_got - dlb_ref))
        ed = float(abs(d_got - d_ref))
        max_abs_dlb = max(max_abs_dlb, edlb)
        max_abs_d = max(max_abs_d, ed)
        if edlb > 2e-2 or ed > 5e-2:
            mismatches += 1
    return {
        "pass": mismatches == 0,
        "cases": len(cases),
        "observed": len(got),
        "mismatches": mismatches,
        "max_abs_dlb": max_abs_dlb,
        "max_abs_d": max_abs_d,
    }


def check_point_engine(log):
    ref = json.loads((ROOT / "reports" / "point_engine_tb_reference.json").read_text())
    rows = {}
    fars = []
    for line in log.read_text(errors="ignore").splitlines():
        if line.startswith("PENG_ROW"):
            fields = line.split()
            rows[int(fields[1])] = int(fields[2], 16)
        elif line.startswith("PENG_FAR"):
            fields = line.split()
            fars.append((int(fields[1]), int(fields[2], 16)))
    mismatches = 0
    max_abs = 0.0
    for e in ref["row_outputs"]:
        got = rows.get(e["idx"])
        if got is None:
            mismatches += 1
            continue
        err = float(abs(bits_f32(got) - np.float32(e["dist"])))
        max_abs = max(max_abs, err)
        if err > 5e-2:
            mismatches += 1
    far_pass = False
    far_err = None
    if fars:
        idx, dist = fars[-1]
        far_err = float(abs(bits_f32(dist) - np.float32(ref["far"]["dist"])))
        far_pass = idx == ref["far"]["idx"] and far_err <= 5e-2
    return {
        "pass": mismatches == 0 and far_pass,
        "row_cases": len(ref["row_outputs"]),
        "row_observed": len(rows),
        "row_mismatches": mismatches,
        "row_max_abs": max_abs,
        "far_observed": len(fars),
        "far_pass": far_pass,
        "far_max_abs": far_err,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("top", choices=["pe", "bucket_cd", "point_engine"])
    ap.add_argument("log", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.top == "pe":
        res = check_pe(args.log)
    elif args.top == "bucket_cd":
        res = check_bucket_cd(args.log)
    else:
        res = check_point_engine(args.log)
    text = json.dumps({args.top: res}, indent=2)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)
    raise SystemExit(0 if res["pass"] else 1)


if __name__ == "__main__":
    main()
