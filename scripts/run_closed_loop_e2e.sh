#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: $0 POINTS_XYZ BUCKETS SAMPLES OUTPUT_DIR [cycle-model args...]" >&2
  exit 2
fi

POINTS=$1
BUCKETS=$2
SAMPLES=$3
OUT=$4
shift 4

PREP="$OUT/preprocessed"
RESULT="$OUT/closed_loop_result.json"
NATIVE_BUILD="$OUT/native-scheduler-build"

cmake -S HOST -B "$OUT/host-build" -DCMAKE_BUILD_TYPE=Release
cmake --build "$OUT/host-build" --parallel

"$OUT/host-build/quickfps_preprocess" \
  --input "$POINTS" \
  --buckets "$BUCKETS" \
  --samples "$SAMPLES" \
  --out "$PREP"

NATIVE_ARGS=()
if [[ "${QFPS_USE_NATIVE_SCHEDULER:-1}" != "0" ]]; then
  bash scripts/build_native_scheduler.sh "$NATIVE_BUILD" >/dev/null
  NATIVE_LIB=$(find "$NATIVE_BUILD" -name 'libquickfps_bucket_scheduler.so' -print -quit)
  if [[ -z "$NATIVE_LIB" ]]; then
    echo "native Bucket scheduler library was not produced" >&2
    exit 1
  fi
  NATIVE_ARGS=(
    --bucket-scheduler native
    --native-bucket-scheduler-lib "$NATIVE_LIB"
  )
fi

PYTHONPATH=cmodel python3 -m quickfps_cycle \
  --preprocessed "$PREP" \
  --samples "$SAMPLES" \
  --output "$RESULT" \
  "${NATIVE_ARGS[@]}" \
  "$@"

python3 - "$RESULT" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text())
if result.get("mode") != "closed-loop":
    raise SystemExit("simulator did not enter closed-loop mode")
if not result.get("matches_golden", False):
    raise SystemExit(
        f"closed-loop mismatch: model={result.get('sampled_indices')} "
        f"golden={result.get('golden_indices')}"
    )
print(
    "CLOSED_LOOP_E2E_PASS "
    f"scheduler={result.get('bucket_scheduler_backend')} "
    f"cycles={result['cycles']} "
    f"sequence={','.join(map(str, result['sampled_indices']))}"
)
PY
