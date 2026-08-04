#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="${ROOT}/build/functional"
mkdir -p "${BUILD}"
mapfile -t RTL_FILES < <(find "${ROOT}/RTL" -type f -name '*.v' | sort)

run_tb() {
    local top="$1"
    local tb="$2"
    local out="${BUILD}/${top}.vvp"
    echo "[compile] ${top}"
    iverilog -g2012 -Wall -s "${top}" -o "${out}" "${tb}" "${RTL_FILES[@]}"
    echo "[run] ${top}"
    vvp "${out}"
}

run_tb tb_max_tree4_tie "${ROOT}/tb/tb_max_tree4_tie.v"
run_tb tb_point_engine_top_tail "${ROOT}/tb/tb_point_engine_top_tail.v"
run_tb tb_point_engine_top_cycle "${ROOT}/tb/tb_point_engine_top_cycle.v"
run_tb tb_quickfps_core_end2end "${ROOT}/tb/tb_quickfps_core_end2end.v"

echo "FUNCTIONAL_CORE_TESTS_PASS"
