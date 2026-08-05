#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BUILD_DIR=${1:-"${ROOT_DIR}/build/event_sim"}

cmake -S "${ROOT_DIR}/event_sim" -B "${BUILD_DIR}" -DCMAKE_BUILD_TYPE=Release
cmake --build "${BUILD_DIR}" --parallel "${CMAKE_BUILD_PARALLEL_LEVEL:-2}"

LIB=$(find "${BUILD_DIR}" -name 'libquickfps_event_sim.so' -print -quit)
if [[ -z "${LIB}" ]]; then
  echo "event simulator library was not produced" >&2
  exit 1
fi
printf '%s\n' "${LIB}"
