#!/usr/bin/env bash
set -euo pipefail

: "${TOP_NAME:?set TOP_NAME}"
: "${TB_FILE:?set TB_FILE}"
: "${TB_TOP:?set TB_TOP}"
: "${STRIP_PATH:?set STRIP_PATH}"
: "${VCD_FILE:?set VCD_FILE}"
: "${TARGET_DB:?set TARGET_DB}"
: "${CELL_VERILOG:?set CELL_VERILOG}"
: "${GATE_PASS_REGEX:?set GATE_PASS_REGEX}"

WORK_ROOT="${WORK_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CLOCK_PERIOD_NS="${CLOCK_PERIOD_NS:-1.0}"
DC_SHELL="${DC_SHELL:-dc_shell}"
VCS="${VCS:-vcs}"
PT_SHELL="${PT_SHELL:-pt_shell}"
SKIP_DC="${SKIP_DC:-0}"
VCD_START_NS="${VCD_START_NS:-}"
export WORK_ROOT TOP_NAME TARGET_DB CLOCK_PERIOD_NS STRIP_PATH VCD_FILE

DC_DIR="${WORK_ROOT}/build/ptpx/${TOP_NAME}/dc"
SIM_DIR="${WORK_ROOT}/build/ptpx/${TOP_NAME}/gate_sim"
mkdir -p "${SIM_DIR}" "$(dirname "${VCD_FILE}")" "${WORK_ROOT}/build/activity"

if [[ "${SKIP_DC}" == "1" ]]; then
    echo "Reusing pre-existing DC artifacts for ${TOP_NAME}"
else
    "${DC_SHELL}" -f "${WORK_ROOT}/scripts/dc_cycle_module.tcl" 2>&1 \
        | tee "${WORK_ROOT}/build/ptpx/${TOP_NAME}/dc.log"
fi

for artifact in \
    "${DC_DIR}/${TOP_NAME}_mapped.v" \
    "${DC_DIR}/${TOP_NAME}.sdc" \
    "${DC_DIR}/${TOP_NAME}.sdf"; do
    if [[ ! -s "${artifact}" ]]; then
        echo "DC did not produce required artifact: ${artifact}" >&2
        exit 1
    fi
done

(
    cd "${SIM_DIR}"
    "${VCS}" -full64 -sverilog -timescale=1ns/1ps \
        "${WORK_ROOT}/${TB_FILE}" \
        "${DC_DIR}/${TOP_NAME}_mapped.v" \
        "${CELL_VERILOG}" \
        -top "${TB_TOP}" \
        -sdf max:"${STRIP_PATH}":"${DC_DIR}/${TOP_NAME}.sdf" \
        -Mdir="${SIM_DIR}/csrc" \
        -o "${SIM_DIR}/simv" 2>&1 \
        | tee "${SIM_DIR}/gate_compile.log"
)
(
    cd "${WORK_ROOT}"
    "${SIM_DIR}/simv" 2>&1 | tee "${SIM_DIR}/gate_sim.log"
)

if ! grep -Eq "${GATE_PASS_REGEX}" "${SIM_DIR}/gate_sim.log"; then
    echo "gate-level golden marker not found for ${TOP_NAME}: ${GATE_PASS_REGEX}" >&2
    exit 1
fi

if [[ ! -f "${VCD_FILE}" ]]; then
    echo "expected VCD was not produced: ${VCD_FILE}" >&2
    exit 1
fi

if [[ -n "${VCD_START_NS}" ]]; then
    VCD_END_NS="$(awk '/^#[0-9]+$/ {last=substr($0, 2)} END {printf "%.6f", last/1000.0}' "${VCD_FILE}")"
    export VCD_START_NS VCD_END_NS
fi

"${PT_SHELL}" -f "${WORK_ROOT}/scripts/ptpx_cycle_module.tcl" 2>&1 \
    | tee "${WORK_ROOT}/build/ptpx/${TOP_NAME}/ptpx.log"

echo "PTPX_COMPLETE top=${TOP_NAME} report=${WORK_ROOT}/build/ptpx/${TOP_NAME}/reports_ptpx/power.rpt"
