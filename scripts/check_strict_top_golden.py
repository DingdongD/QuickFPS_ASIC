#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


def check_point_engine_top(text: str):
    match = re.search(r"PTOP_PUSH\s+(\d+)\s+LATENCY\s+(\d+)", text)
    failures = re.findall(r"PTOP_(?:CYCLE|DATA)_FAIL", text)
    return {
        "pass": bool(match) and not failures and "PTOP_CYCLE_PASS" in text,
        "push_cycle": int(match.group(1)) if match else None,
        "latency_cycles": int(match.group(2)) if match else None,
        "expected_latency_cycles": 38,
        "failure_markers": failures,
    }


def check_bucket_engine(text: str):
    match = re.search(
        r"BENG_STRICT_PASS\s+latency_cycles=(\d+)\s+requests=(\d+)\s+responses=(\d+)",
        text,
    )
    fatal = "$fatal" in text or "BENG count mismatch" in text or "mismatch" in text
    return {
        "pass": bool(match) and not fatal,
        "latency_cycles": int(match.group(1)) if match else None,
        "requests": int(match.group(2)) if match else None,
        "responses": int(match.group(3)) if match else None,
        "expected_requests": 7,
        "expected_responses": 7,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("top", choices=["point_engine_top", "bucket_engine"])
    parser.add_argument("log", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    text = args.log.read_text(errors="ignore")
    if args.top == "point_engine_top":
        result = check_point_engine_top(text)
    else:
        result = check_bucket_engine(text)
    output = json.dumps({args.top: result}, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output + "\n")
    print(output)
    raise SystemExit(0 if result["pass"] else 1)


if __name__ == "__main__":
    main()
