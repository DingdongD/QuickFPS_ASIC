#!/usr/bin/env bash
set -euo pipefail

: "${TOP_NAME:?set TOP_NAME}"
: "${TB_FILE:?set TB_FILE}"
: "${TB_TOP:?set TB_TOP}"
: "${STRIP_PATH:?set STRIP_PATH}"
: "${VCD_FILE:?set VCD_FILE}"
: "${TARGET_DB:?set TARGET_DB}"
: "${CELL_VERILOG:?set CELL_VERILOG}"

WORK_ROOT="${WORK_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CLOCK_PERIOD_NS="${CLOCK_PERIOD_NS:-1.0}"
DC_SHELL="${DC_SHELL:-dc_shell}"
VCS="${VCS:-vcs}"
PT_SHELL="${PT_SHELL:-pt_shell}"
export WORK_ROOT TOP_NAME TARGET_DB CLOCK_PERIOD_NS STRIP_PATH VCD_FILE

DC_DIR="${WORK_ROOT}/build/ptpx/${TOP_NAME}/dc"
SIM_DIR="${WORK_ROOT}/build/ptpx/${TOP_NAME}/gate_sim"
mkdir -p "${SIM_DIR}" "$(dirname "${VCD_FILE}")" "${WORK_ROOT}/build/activity"

"${DC_SHELL}" -f "${WORK_ROOT}/scripts/dc_cycle_module.tcl" \
    | tee "${WORK_ROOT}/build/ptpx/${TOP_NAME}/dc.log"

"${VCS}" -full64 -sverilog -timescale=1ns/1ps \
    "${WORK_ROOT}/${TB_FILE}" \
    "${DC_DIR}/${TOP_NAME}_mapped.v" \
    "${CELL_VERILOG}" \
    -top "${TB_TOP}" \
    -sdf max:"${STRIP_PATH}":"${DC_DIR}/${TOP_NAME}.sdf" \
    -o "${SIM_DIR}/simv"
(
    cd "${WORK_ROOT}"
    "${SIM_DIR}/simv" | tee "${SIM_DIR}/gate_sim.log"
)

if [[ ! -f "${VCD_FILE}" ]]; then
    echo "expected VCD was not produced: ${VCD_FILE}" >&2
    exit 1
fi

"${PT_SHELL}" -f "${WORK_ROOT}/scripts/ptpx_cycle_module.tcl" \
    | tee "${WORK_ROOT}/build/ptpx/${TOP_NAME}/ptpx.log"

echo "PTPX_COMPLETE top=${TOP_NAME} report=${WORK_ROOT}/build/ptpx/${TOP_NAME}/reports_ptpx/power.rpt"
