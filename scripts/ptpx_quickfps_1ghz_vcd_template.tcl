set TOP_NAME [getenv TOP_NAME]
set WORK_ROOT [getenv WORK_ROOT]
set REPORT_DIR "$WORK_ROOT/reports_1ghz/${TOP_NAME}_ptpx_vcd"
set OUTPUT_DIR "$WORK_ROOT/outputs_1ghz/$TOP_NAME"
set VCD_FILE "$WORK_ROOT/activity_1ghz/${TOP_NAME}_gate.vcd"
file mkdir $REPORT_DIR

set_app_var search_path [list \
    "$WORK_ROOT/RTL/bucket_engine" \
    "$WORK_ROOT/RTL/point_engine" \
    "/home/xuliang/lib/tsmc28_bwp40p140/tcbn28hpcplusbwp40p140/nldm" \
]
set_app_var target_library [list "/home/xuliang/lib/tsmc28_bwp40p140/tcbn28hpcplusbwp40p140/nldm/tcbn28hpcplusbwp40p140ssg0p81v125c.db"]
set_app_var link_library [concat "*" $target_library]
set_app_var power_enable_analysis true

read_verilog "$OUTPUT_DIR/${TOP_NAME}_mapped.v"
current_design $TOP_NAME
link
read_sdc "$OUTPUT_DIR/${TOP_NAME}.sdc"
if {[sizeof_collection [get_ports -quiet rst_n]] > 0} {
    set_case_analysis 1 [get_ports rst_n]
    set_ideal_network -no_propagate [get_ports rst_n]
}
if {[sizeof_collection [all_outputs]] > 0} {
    set_load 0.005 [all_outputs]
}
if {[file exists $VCD_FILE]} {
    read_vcd -strip_path "tb_${TOP_NAME}_gate/dut" $VCD_FILE
}
check_timing > "$REPORT_DIR/check_timing.rpt"
update_timing
update_power
report_analysis_coverage > "$REPORT_DIR/analysis_coverage.rpt"
report_switching_activity -list_not_annotated > "$REPORT_DIR/not_annotated.rpt"
report_timing -delay_type max -slack_lesser_than 1000000 \
    -max_paths 20 -significant_digits 8 > "$REPORT_DIR/timing_setup.rpt"
report_timing -delay_type min -slack_lesser_than 1000000 \
    -max_paths 20 -significant_digits 8 > "$REPORT_DIR/timing_hold.rpt"
report_constraint -all_violators -significant_digits 4 > "$REPORT_DIR/constraints.rpt"
report_power -hierarchy > "$REPORT_DIR/power_ptpx_vcd.rpt"
quit
