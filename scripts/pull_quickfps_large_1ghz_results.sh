#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 /home/xuliang/quickfps_large_1ghz_<stamp>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_ROOT="$1"
REMOTE_HOST="${QUICKFPS_REMOTE_HOST:-}"
REMOTE_PORT="${QUICKFPS_REMOTE_PORT:-22}"
PASS="${QUICKFPS_REMOTE_PASS:-}"
STAMP="$(basename "${REMOTE_ROOT}" | sed 's/^quickfps_large_1ghz_//')"
LOCAL_OUT="${ROOT}/remote/remote_large_1ghz_${STAMP}"

if [ -z "${REMOTE_HOST}" ] || [ -z "${PASS}" ]; then
  echo "error: set QUICKFPS_REMOTE_HOST and QUICKFPS_REMOTE_PASS" >&2
  exit 2
fi

mkdir -p "${LOCAL_OUT}"
sshpass -p "${PASS}" ssh -p "${REMOTE_PORT}" -o StrictHostKeyChecking=no "${REMOTE_HOST}" /bin/bash -s <<REMOTE
cd "${REMOTE_ROOT}"
if [ ! -f quickfps_large_1ghz_results.tgz ]; then
  tar -czf quickfps_large_1ghz_results.tgz logs reports_1ghz outputs_1ghz activity_1ghz reports/point_engine_tb_reference.json || true
fi
REMOTE
sshpass -p "${PASS}" scp -P "${REMOTE_PORT}" -o StrictHostKeyChecking=no \
  "${REMOTE_HOST}:${REMOTE_ROOT}/quickfps_large_1ghz_results.tgz" "${LOCAL_OUT}/"
tar -C "${LOCAL_OUT}" -xzf "${LOCAL_OUT}/quickfps_large_1ghz_results.tgz"

if [ -f "${LOCAL_OUT}/logs/vcs_1ghz_point_engine_sim.log" ]; then
  python3 "${ROOT}/scripts/check_gate_golden.py" point_engine \
    "${LOCAL_OUT}/logs/vcs_1ghz_point_engine_sim.log" \
    --out "${ROOT}/reports/point_engine_gate_golden_${STAMP}.json"
fi

echo "${LOCAL_OUT}"
