#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
REMOTE_HOST="${QUICKFPS_REMOTE_HOST:-}"
REMOTE_PORT="${QUICKFPS_REMOTE_PORT:-22}"
REMOTE_BASE="${QUICKFPS_REMOTE_BASE:-/home/xuliang}"
REMOTE_ROOT="${REMOTE_BASE}/quickfps_ppa_${STAMP}"
PASS="${QUICKFPS_REMOTE_PASS:-}"

if [ -z "${REMOTE_HOST}" ] || [ -z "${PASS}" ]; then
  echo "error: set QUICKFPS_REMOTE_HOST and QUICKFPS_REMOTE_PASS" >&2
  exit 2
fi

tarball="${ROOT}/remote/quickfps_src_${STAMP}.tgz"
mkdir -p "${ROOT}/remote"
tar -C "${ROOT}" -czf "${tarball}" RTL tb scripts reports/quickfps_golden_summary.txt task_plan.md findings.md progress.md

sshpass -p "${PASS}" ssh -p "${REMOTE_PORT}" -o StrictHostKeyChecking=no "${REMOTE_HOST}" "mkdir -p '${REMOTE_ROOT}'"
sshpass -p "${PASS}" scp -P "${REMOTE_PORT}" -o StrictHostKeyChecking=no "${tarball}" "${REMOTE_HOST}:${REMOTE_ROOT}/quickfps_src.tgz"

sshpass -p "${PASS}" ssh -p "${REMOTE_PORT}" -o StrictHostKeyChecking=no "${REMOTE_HOST}" bash -s <<REMOTE
set -euo pipefail
cd "${REMOTE_ROOT}"
tar -xzf quickfps_src.tgz
mkdir -p logs reports outputs work
source /tools/synopsys2022/eda_s.sh
unset VCS_ARCH_OVERRIDE
unset VCS_ARCH
export VCS_TARGET_ARCH=linux64
export SNPSLMD_LICENSE_FILE=27000@EDA
export LM_LICENSE_FILE=/tools/synopsys2022/Synopsys.dat
tops="fp32_add fp32_sub fp32_mul bucket_cd pe point_engine bucketdist_skip_top point_engine_top bucket_engine"
for top in \$tops; do
  echo "[DC] \$top"
  mkdir -p "work/\$top"
  TOP_NAME="\$top" WORK_ROOT="${REMOTE_ROOT}" dc_shell -f scripts/dc_quickfps_template.tcl > "logs/dc_\${top}.log" 2>&1 || echo "DC_FAIL \$top" | tee "logs/dc_\${top}.status"
  if [ -f "outputs/\$top/\${top}_mapped.v" ]; then
    echo "[PTPX] \$top"
    TOP_NAME="\$top" WORK_ROOT="${REMOTE_ROOT}" pt_shell -f scripts/ptpx_quickfps_template.tcl > "logs/ptpx_\${top}.log" 2>&1 || echo "PTPX_FAIL \$top" | tee "logs/ptpx_\${top}.status"
  fi
done
tar -czf quickfps_results.tgz logs reports outputs
REMOTE

local_out="${ROOT}/remote/remote_results_${STAMP}"
mkdir -p "${local_out}"
sshpass -p "${PASS}" scp -P "${REMOTE_PORT}" -o StrictHostKeyChecking=no "${REMOTE_HOST}:${REMOTE_ROOT}/quickfps_results.tgz" "${local_out}/"
tar -C "${local_out}" -xzf "${local_out}/quickfps_results.tgz"
echo "${local_out}"
