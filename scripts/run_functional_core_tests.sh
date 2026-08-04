#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD="${ROOT}/build/functional"
mkdir -p "${BUILD}" "${ROOT}/build/activity"
mapfile -t RTL_FILES < <(find "${ROOT}/RTL" -type f -name '*.v' | sort)

run_tb() {
    local top="$1"
    local tb="$2"
    local out="${BUILD}/${top}.vvp"
    local log="${BUILD}/${top}.log"
    echo "[compile] ${top}"
    iverilog -g2012 -Wall -s "${top}" -o "${out}" "${tb}" "${RTL_FILES[@]}"
    echo "[run] ${top}"
    (cd "${ROOT}" && vvp "${out}") | tee "${log}"
}

run_tb tb_max_tree4_tie "${ROOT}/tb/tb_max_tree4_tie.v"
run_tb tb_point_engine_top_tail "${ROOT}/tb/tb_point_engine_top_tail.v"
run_tb tb_point_engine_top_cycle "${ROOT}/tb/tb_point_engine_top_cycle.v"
run_tb tb_quickfps_core_end2end "${ROOT}/tb/tb_quickfps_core_end2end.v"
run_tb tb_bucket_decision_pipe "${ROOT}/tb/tb_bucket_decision_pipe.v"
run_tb tb_bucket_decision_activity "${ROOT}/tb/tb_bucket_decision_activity.v"
run_tb tb_pingpong_chunk_ctrl "${ROOT}/tb/tb_pingpong_chunk_ctrl.v"
run_tb tb_pingpong_chunk_activity "${ROOT}/tb/tb_pingpong_chunk_activity.v"
run_tb tb_sram_1r1w_activity "${ROOT}/tb/tb_sram_1r1w_activity.v"
run_tb tb_axi_burst_reader_activity "${ROOT}/tb/tb_axi_burst_reader_activity.v"
run_tb tb_axi_burst_writer_activity "${ROOT}/tb/tb_axi_burst_writer_activity.v"
run_tb tb_axi_dma_activity "${ROOT}/tb/tb_axi_dma_activity.v"
run_tb tb_quickfps_stream_subsystem "${ROOT}/tb/tb_quickfps_stream_subsystem.v"

echo "FUNCTIONAL_CORE_TESTS_PASS"
