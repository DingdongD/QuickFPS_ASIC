#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
    echo "usage: $0 /home/xuliang/quickfps_cycle_strict_1ghz_<stamp>" >&2
    exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE_ROOT="$1"
REMOTE_HOST="${QUICKFPS_REMOTE_HOST:-}"
REMOTE_PORT="${QUICKFPS_REMOTE_PORT:-22}"
PASS="${QUICKFPS_REMOTE_PASS:-}"
STAMP="$(basename "${REMOTE_ROOT}" | sed 's/^quickfps_cycle_strict_1ghz_//')"
LOCAL_OUT="${ROOT}/remote/remote_cycle_strict_1ghz_${STAMP}"

if [[ -z "${REMOTE_HOST}" || -z "${PASS}" ]]; then
    echo "error: set QUICKFPS_REMOTE_HOST and QUICKFPS_REMOTE_PASS" >&2
    exit 2
fi

mkdir -p "${LOCAL_OUT}"
sshpass -p "${PASS}" scp -P "${REMOTE_PORT}" -o StrictHostKeyChecking=no \
    "${REMOTE_HOST}:${REMOTE_ROOT}/quickfps_cycle_strict_results.tgz" \
    "${LOCAL_OUT}/"
tar -C "${LOCAL_OUT}" -xzf "${LOCAL_OUT}/quickfps_cycle_strict_results.tgz"
echo "${LOCAL_OUT}"
