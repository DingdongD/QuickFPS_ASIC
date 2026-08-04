#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 "${ROOT}/scripts/make_gate_tbs_1ghz.py"
STAMP="$(date +%Y%m%d_%H%M%S)"
REMOTE_HOST="${QUICKFPS_REMOTE_HOST:-}"
REMOTE_PORT="${QUICKFPS_REMOTE_PORT:-22}"
REMOTE_BASE="${QUICKFPS_REMOTE_BASE:-/home/xuliang}"
REMOTE_ROOT="${REMOTE_BASE}/quickfps_gate_1ghz_${STAMP}"
PASS="${QUICKFPS_REMOTE_PASS:-}"

if [ -z "${REMOTE_HOST}" ] || [ -z "${PASS}" ]; then
  echo "error: set QUICKFPS_REMOTE_HOST and QUICKFPS_REMOTE_PASS" >&2
  exit 2
fi

tarball="${ROOT}/remote/quickfps_gate_1ghz_src_${STAMP}.tgz"
mkdir -p "${ROOT}/remote"
tar -C "${ROOT}" -czf "${tarball}" RTL tb scripts reports/quickfps_golden_summary.txt

sshpass -p "${PASS}" ssh -p "${REMOTE_PORT}" -o StrictHostKeyChecking=no "${REMOTE_HOST}" "mkdir -p '${REMOTE_ROOT}'"
sshpass -p "${PASS}" scp -P "${REMOTE_PORT}" -o StrictHostKeyChecking=no "${tarball}" "${REMOTE_HOST}:${REMOTE_ROOT}/quickfps_src.tgz"

sshpass -p "${PASS}" ssh -p "${REMOTE_PORT}" -o StrictHostKeyChecking=no "${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
cd "${REMOTE_ROOT}"
tar -xzf quickfps_src.tgz
mkdir -p logs reports_1ghz outputs_1ghz work_1ghz activity_1ghz sim_1ghz
source /tools/synopsys2022/eda_s.sh
unset VCS_ARCH_OVERRIDE
unset VCS_ARCH
export VCS_TARGET_ARCH=linux64
export SNPSLMD_LICENSE_FILE=27000@EDA
export LM_LICENSE_FILE=/tools/synopsys2022/Synopsys.dat
STD_VERILOG="/home/xuliang/lib/tsmc28_bwp40p140/tcbn28hpcplusbwp40p140/verilog/tcbn28hpcplusbwp40p140.v"
tops="pe bucket_cd point_engine point_engine_top bucket_engine"
for top in \$tops; do
  echo "[DC 1GHz] \$top"
  mkdir -p "work_1ghz/\$top"
  TOP_NAME="\$top" WORK_ROOT="${REMOTE_ROOT}" dc_shell -f scripts/dc_quickfps_1ghz_template.tcl > "logs/dc_1ghz_\${top}.log" 2>&1 || echo "DC_FAIL \$top" | tee "logs/dc_1ghz_\${top}.status"
done
for top in pe bucket_cd; do
  if [ -f "outputs_1ghz/\$top/\${top}_mapped.v" ]; then
    echo "[Gate VCS 1GHz] \$top"
    vcs -full64 -sverilog +v2k -timescale=1ns/1ps +neg_tchk +notimingcheck \\
      "tb/tb_\${top}_gate.v" "outputs_1ghz/\$top/\${top}_mapped.v" "\$STD_VERILOG" \\
      -o "sim_1ghz/\${top}_gate.simv" > "logs/vcs_1ghz_\${top}_compile.log" 2>&1 || echo "VCS_COMPILE_FAIL \$top" | tee "logs/vcs_1ghz_\${top}.status"
    if [ -x "sim_1ghz/\${top}_gate.simv" ]; then
      "sim_1ghz/\${top}_gate.simv" > "logs/vcs_1ghz_\${top}_sim.log" 2>&1 || echo "VCS_SIM_FAIL \$top" | tee -a "logs/vcs_1ghz_\${top}.status"
      echo "[PTPX VCD 1GHz] \$top"
      TOP_NAME="\$top" WORK_ROOT="${REMOTE_ROOT}" pt_shell -f scripts/ptpx_quickfps_1ghz_vcd_template.tcl > "logs/ptpx_1ghz_vcd_\${top}.log" 2>&1 || echo "PTPX_FAIL \$top" | tee -a "logs/ptpx_1ghz_vcd_\${top}.status"
    fi
  fi
done
tar -czf quickfps_gate_1ghz_results.tgz logs reports_1ghz outputs_1ghz activity_1ghz
REMOTE

local_out="${ROOT}/remote/remote_gate_1ghz_${STAMP}"
mkdir -p "${local_out}"
sshpass -p "${PASS}" scp -P "${REMOTE_PORT}" -o StrictHostKeyChecking=no "${REMOTE_HOST}:${REMOTE_ROOT}/quickfps_gate_1ghz_results.tgz" "${local_out}/"
tar -C "${local_out}" -xzf "${local_out}/quickfps_gate_1ghz_results.tgz"
echo "${local_out}"
