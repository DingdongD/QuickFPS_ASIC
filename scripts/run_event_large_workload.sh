#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: $0 PREPROCESSED_DIR SAMPLES OUTPUT_JSON BUILD_DIR [event-cli args...]" >&2
  exit 2
fi

PREPROCESSED=$1
SAMPLES=$2
OUTPUT=$3
BUILD_DIR=$4
shift 4

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

bash "${ROOT_DIR}/scripts/build_event_sim.sh" "${BUILD_DIR}" >/dev/null
LIB=$(find "${BUILD_DIR}" -name 'libquickfps_event_sim.so' -print -quit)
if [[ -z "${LIB}" ]]; then
  echo "event simulator library was not produced" >&2
  exit 1
fi

PYTHONPATH="${ROOT_DIR}/cmodel" \
python3 -m quickfps_cycle.event_cli \
  --preprocessed "${PREPROCESSED}" \
  --samples "${SAMPLES}" \
  --event-sim-lib "${LIB}" \
  --max-hardware-cycles 10000000000 \
  --progress-every 1024 \
  --output "${OUTPUT}" \
  "$@"
