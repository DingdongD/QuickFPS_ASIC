set TOP_NAME [getenv TOP_NAME]
set WORK_ROOT [getenv WORK_ROOT]
set REPORT_DIR "$WORK_ROOT/reports_1ghz/$TOP_NAME"
set OUTPUT_DIR "$WORK_ROOT/outputs_1ghz/$TOP_NAME"
file mkdir $REPORT_DIR
file mkdir $OUTPUT_DIR

set_app_var search_path [list \
    "$WORK_ROOT/RTL/bucket_engine" \
    "$WORK_ROOT/RTL/point_engine" \
    "/home/xuliang/lib/tsmc28_bwp40p140/tcbn28hpcplusbwp40p140/nldm" \
]
set_app_var target_library [list "/home/xuliang/lib/tsmc28_bwp40p140/tcbn28hpcplusbwp40p140/nldm/tcbn28hpcplusbwp40p140ssg0p81v125c.db"]
set_app_var link_library [concat "*" $target_library]
define_design_lib WORK -path "$WORK_ROOT/work_1ghz/$TOP_NAME"

set rtl_files [list \
    "$WORK_ROOT/RTL/point_engine/fp32_add.v" \
    "$WORK_ROOT/RTL/point_engine/fp32_sub.v" \
    "$WORK_ROOT/RTL/point_engine/fp32_mul.v" \
    "$WORK_ROOT/RTL/point_engine/max_tree4.v" \
    "$WORK_ROOT/RTL/point_engine/pe.v" \
    "$WORK_ROOT/RTL/point_engine/pe_row.v" \
    "$WORK_ROOT/RTL/point_engine/point_engine.v" \
    "$WORK_ROOT/RTL/bucket_engine/fp32_box_gap.v" \
    "$WORK_ROOT/RTL/bucket_engine/fp32_bucketdist_prune_pipe.v" \
    "$WORK_ROOT/RTL/bucket_engine/bucket_cd.v" \
    "$WORK_ROOT/RTL/bucket_engine/bucket_ib.v" \
    "$WORK_ROOT/RTL/bucket_engine/sync_fifo.v" \
    "$WORK_ROOT/RTL/bucket_engine/bucketdist_skip_top.v" \
    "$WORK_ROOT/RTL/bucket_engine/point_engine_top.v" \
    "$WORK_ROOT/RTL/bucket_engine/bucket_engine.v" \
]

analyze -format verilog $rtl_files
elaborate $TOP_NAME
current_design $TOP_NAME
link
check_design > "$REPORT_DIR/check_design.rpt"

if {[sizeof_collection [get_ports -quiet clk]] > 0} {
    create_clock -name clk -period 1.0 [get_ports clk]
    if {[sizeof_collection [get_ports -quiet rst_n]] > 0} {
        set_case_analysis 1 [get_ports rst_n]
    }
    set_clock_uncertainty -setup 0.03 [get_clocks clk]
    set_clock_uncertainty -hold 0.00 [get_clocks clk]
    set_input_delay 0.05 -clock clk [remove_from_collection [all_inputs] [get_ports clk]]
    set_output_delay 0.05 -clock clk [all_outputs]
    set_load 0.005 [all_outputs]
    set_fix_hold [get_clocks clk]
} else {
    set_max_delay 1.0 -from [all_inputs] -to [all_outputs]
    set_load 0.005 [all_outputs]
}

compile_ultra

write -format verilog -hierarchy -output "$OUTPUT_DIR/${TOP_NAME}_mapped.v"
write_sdc "$OUTPUT_DIR/${TOP_NAME}.sdc"
write_sdf "$OUTPUT_DIR/${TOP_NAME}.sdf"
report_area -hierarchy > "$REPORT_DIR/area.rpt"
report_timing -delay_type max -max_paths 20 -significant_digits 4 > "$REPORT_DIR/timing_setup.rpt"
report_timing -delay_type min -max_paths 20 -significant_digits 4 > "$REPORT_DIR/timing_hold.rpt"
report_constraint -all_violators -significant_digits 4 > "$REPORT_DIR/constraints.rpt"
report_power -hierarchy > "$REPORT_DIR/power_dc.rpt"
quit
