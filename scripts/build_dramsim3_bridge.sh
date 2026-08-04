#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="${ROOT}/build/dramsim3_bridge"

cmake -S "${ROOT}/dramsim3_bridge" -B "${BUILD}" \
    -DCMAKE_BUILD_TYPE=Release
cmake --build "${BUILD}" --parallel "${JOBS:-2}"

LIB="$(find "${BUILD}" -name 'libquickfps_dramsim3_bridge.so' -print -quit)"
CONFIG="${BUILD}/_deps/dramsim3_external-src/configs/DDR4_8Gb_x8_2400.ini"

if [[ -z "${LIB}" || ! -f "${LIB}" ]]; then
    echo "DRAMsim3 bridge library was not produced" >&2
    exit 1
fi
if [[ ! -f "${CONFIG}" ]]; then
    echo "Pinned DDR4-2400 configuration was not fetched" >&2
    exit 1
fi

cat <<EOF
DRAMSIM3_BRIDGE=${LIB}
DRAMSIM3_CONFIG=${CONFIG}

Example:
PYTHONPATH=${ROOT}/cmodel python3 -m quickfps_cycle.cli \\
  --workload ${ROOT}/build/quickfps_workload.json \\
  --dramsim3-lib ${LIB} \\
  --dramsim3-config ${CONFIG} \\
  --output ${ROOT}/build/cycle_dramsim3.json
EOF
