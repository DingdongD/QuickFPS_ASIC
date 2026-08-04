set TOP_NAME [getenv TOP_NAME]
set WORK_ROOT [getenv WORK_ROOT]
set REPORT_DIR "$WORK_ROOT/reports/${TOP_NAME}_ptpx"
set OUTPUT_DIR "$WORK_ROOT/outputs/$TOP_NAME"
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
check_timing > "$REPORT_DIR/check_timing.rpt"
update_timing
set_switching_activity -static_probability 0.2 -toggle_rate 0.05 [all_inputs]
update_power
report_analysis_coverage > "$REPORT_DIR/analysis_coverage.rpt"
report_timing -delay_type max -max_paths 20 -significant_digits 4 > "$REPORT_DIR/timing_setup.rpt"
report_timing -delay_type min -max_paths 20 -significant_digits 4 > "$REPORT_DIR/timing_hold.rpt"
report_power -hierarchy > "$REPORT_DIR/power_ptpx.rpt"
quit
