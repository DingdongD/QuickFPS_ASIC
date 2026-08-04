#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="$(date +%Y%m%d_%H%M%S)"
REMOTE_HOST="${QUICKFPS_REMOTE_HOST:-}"
REMOTE_PORT="${QUICKFPS_REMOTE_PORT:-22}"
REMOTE_BASE="${QUICKFPS_REMOTE_BASE:-/home/xuliang}"
REMOTE_ROOT="${REMOTE_BASE}/quickfps_cycle_strict_1ghz_${STAMP}"
REMOTE_REUSE_DC_ROOT="${QUICKFPS_REMOTE_REUSE_DC_ROOT:-}"
REMOTE_REUSE_DC_EXCLUDE="${QUICKFPS_REMOTE_REUSE_DC_EXCLUDE:-}"
PASS="${QUICKFPS_REMOTE_PASS:-}"

if [[ -z "${REMOTE_HOST}" || -z "${PASS}" ]]; then
    echo "error: set QUICKFPS_REMOTE_HOST and QUICKFPS_REMOTE_PASS" >&2
    exit 2
fi

mkdir -p "${ROOT}/remote"
tarball="${ROOT}/remote/quickfps_cycle_strict_src_${STAMP}.tgz"
tar -C "${ROOT}" -czf "${tarball}" RTL tb scripts ptpx cmodel

sshpass -p "${PASS}" ssh -p "${REMOTE_PORT}" -o StrictHostKeyChecking=no \
    "${REMOTE_HOST}" "mkdir -p '${REMOTE_ROOT}'"
sshpass -p "${PASS}" scp -P "${REMOTE_PORT}" -o StrictHostKeyChecking=no \
    "${tarball}" "${REMOTE_HOST}:${REMOTE_ROOT}/quickfps_src.tgz"

sshpass -p "${PASS}" ssh -p "${REMOTE_PORT}" -o StrictHostKeyChecking=no \
    "${REMOTE_HOST}" /bin/bash -c "cat > '${REMOTE_ROOT}/run.sh'" <<REMOTE
#!/usr/bin/env bash
set -euo pipefail
cd "${REMOTE_ROOT}"
tar -xzf quickfps_src.tgz
mkdir -p build/activity activity_1ghz logs
source /tools/synopsys2022/eda_s.sh
unset VCS_ARCH_OVERRIDE VCS_ARCH
export VCS_TARGET_ARCH=linux64
export SNPSLMD_LICENSE_FILE=27000@EDA
export LM_LICENSE_FILE=/tools/synopsys2022/Synopsys.dat
TARGET_DB=/home/xuliang/lib/tsmc28_bwp40p140/tcbn28hpcplusbwp40p140/nldm/tcbn28hpcplusbwp40p140ssg0p81v125c.db
CELL_VERILOG=/home/xuliang/lib/tsmc28_bwp40p140/tcbn28hpcplusbwp40p140/verilog/tcbn28hpcplusbwp40p140.v
REUSE_DC_ROOT="${REMOTE_REUSE_DC_ROOT}"
REUSE_DC_EXCLUDE=" ${REMOTE_REUSE_DC_EXCLUDE} "

run_module() {
    local top="\$1"
    local tb_file="\$2"
    local tb_top="\$3"
    local strip_path="\$4"
    local vcd_file="\$5"
    local pass_regex="\$6"
    local vcd_start_ns="\$7"
    local dc_timing_high_effort=0
    local dc_opt_clock_period_ns=1.0
    local dc_reuse_ddc=""
    if [[ "\$top" == "bucket_decision_pipe" ]]; then
        dc_timing_high_effort=1
        dc_opt_clock_period_ns=0.995
    fi
    local skip_dc=0
    if [[ -n "\$REUSE_DC_ROOT" && "\$REUSE_DC_EXCLUDE" != *" \$top "* ]]; then
        local prior="\$REUSE_DC_ROOT/build/ptpx/\$top"
        local current="${REMOTE_ROOT}/build/ptpx/\$top"
        if [[ -s "\$prior/dc/\${top}_mapped.v" &&
              -s "\$prior/dc/\${top}.sdc" &&
              -s "\$prior/dc/\${top}.sdf" ]]; then
            mkdir -p "\$current"
            cp -a "\$prior/dc" "\$current/"
            cp -a "\$prior/reports_dc" "\$current/"
            cp -a "\$prior/dc.log" "\$current/" 2>/dev/null || true
            skip_dc=1
        fi
    fi
    if [[ -n "\$REUSE_DC_ROOT" && "\$REUSE_DC_EXCLUDE" == *" \$top "* ]]; then
        local prior_ddc="\$REUSE_DC_ROOT/build/ptpx/\$top/dc/\${top}.ddc"
        if [[ -s "\$prior_ddc" ]]; then
            dc_reuse_ddc="\$prior_ddc"
        fi
    fi
    echo "[strict gate-VCD PTPX] \$top"
    TOP_NAME="\$top" \
    TB_FILE="\$tb_file" \
    TB_TOP="\$tb_top" \
    STRIP_PATH="\$strip_path" \
    VCD_FILE="${REMOTE_ROOT}/\$vcd_file" \
    VCD_START_NS="\$vcd_start_ns" \
    GATE_PASS_REGEX="\$pass_regex" \
    TARGET_DB="\$TARGET_DB" \
    CELL_VERILOG="\$CELL_VERILOG" \
    WORK_ROOT="${REMOTE_ROOT}" \
    CLOCK_PERIOD_NS=1.0 \
    DC_TIMING_HIGH_EFFORT="\$dc_timing_high_effort" \
    DC_OPT_CLOCK_PERIOD_NS="\$dc_opt_clock_period_ns" \
    DC_REUSE_DDC="\$dc_reuse_ddc" \
    SKIP_DC="\$skip_dc" \
        bash scripts/run_cycle_ptpx.sh
}

run_compute() {
    run_module point_engine_top \
        tb/tb_point_engine_top_gate.v tb_point_engine_top_gate \
        tb_point_engine_top_gate/dut activity_1ghz/point_engine_top_gate.vcd \
        PTOP_CYCLE_PASS 3.0
}

run_leaf() {
    run_module bucket_decision_pipe \
        tb/tb_bucket_decision_activity.v tb_bucket_decision_activity \
        tb_bucket_decision_activity/dut build/activity/bucket_decision_pipe.vcd \
        BUCKET_DECISION_ACTIVITY_PASS 5.0
    run_module axi_burst_reader \
        tb/tb_axi_burst_reader_activity.v tb_axi_burst_reader_activity \
        tb_axi_burst_reader_activity/dut build/activity/axi_burst_reader.vcd \
        AXI_READER_PASS 5.0
    run_module axi_burst_writer \
        tb/tb_axi_burst_writer_activity.v tb_axi_burst_writer_activity \
        tb_axi_burst_writer_activity/dut build/activity/axi_burst_writer.vcd \
        AXI_WRITER_PASS 5.0
    run_module pingpong_chunk_ctrl \
        tb/tb_pingpong_chunk_activity.v tb_pingpong_chunk_activity \
        tb_pingpong_chunk_activity/dut build/activity/pingpong_chunk_ctrl.vcd \
        PINGPONG_ACTIVITY_PASS 5.0
}

# Keep the large FP compute hierarchy separate from the smaller control/DMA set.
run_compute > logs/compute.log 2>&1 &
compute_pid=\$!
run_leaf > logs/leaf.log 2>&1 &
leaf_pid=\$!

compute_status=0
leaf_status=0
wait "\$compute_pid" || compute_status=\$?
wait "\$leaf_pid" || leaf_status=\$?
if [[ "\$compute_status" -ne 0 || "\$leaf_status" -ne 0 ]]; then
    echo "strict module failure compute=\$compute_status leaf=\$leaf_status" >&2
    exit 1
fi

run_module quickfps_stream_subsystem \
    tb/tb_quickfps_stream_subsystem.v tb_quickfps_stream_subsystem \
    tb_quickfps_stream_subsystem/dut build/activity/quickfps_stream_subsystem.vcd \
    STREAM_SUBSYSTEM_PASS 5.0 > logs/aggregate.log 2>&1
tar -czf quickfps_cycle_strict_results.tgz build activity_1ghz logs ptpx
echo DONE > DONE
REMOTE

sshpass -p "${PASS}" ssh -p "${REMOTE_PORT}" -o StrictHostKeyChecking=no \
    "${REMOTE_HOST}" /bin/bash -s <<REMOTE
chmod +x "${REMOTE_ROOT}/run.sh"
nohup "${REMOTE_ROOT}/run.sh" > "${REMOTE_ROOT}/run.nohup.log" 2>&1 &
echo \$! > "${REMOTE_ROOT}/PID"
echo "${REMOTE_ROOT}"
REMOTE
