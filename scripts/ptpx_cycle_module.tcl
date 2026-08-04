set TOP_NAME [getenv TOP_NAME]
set WORK_ROOT [getenv WORK_ROOT]
set TARGET_DB [getenv TARGET_DB]
set VCD_FILE [getenv VCD_FILE]
set STRIP_PATH [getenv STRIP_PATH]

if {$TOP_NAME eq "" || $WORK_ROOT eq "" || $TARGET_DB eq "" ||
    $VCD_FILE eq "" || $STRIP_PATH eq ""} {
    error "TOP_NAME, WORK_ROOT, TARGET_DB, VCD_FILE, and STRIP_PATH must be set"
}

set DC_DIR "$WORK_ROOT/build/ptpx/$TOP_NAME/dc"
set RPT_DIR "$WORK_ROOT/build/ptpx/$TOP_NAME/reports_ptpx"
file mkdir $RPT_DIR

set_app_var target_library [list $TARGET_DB]
set_app_var link_library [concat "*" $target_library]
set_app_var search_path [concat [list [file dirname $TARGET_DB]] $search_path]
set_app_var power_enable_analysis true

read_verilog "$DC_DIR/${TOP_NAME}_mapped.v"
current_design $TOP_NAME
link
read_sdc "$DC_DIR/${TOP_NAME}.sdc"
if {[sizeof_collection [get_ports -quiet rst_n]] > 0} {
    set_case_analysis 1 [get_ports rst_n]
    set_ideal_network -no_propagate [get_ports rst_n]
}
if {[sizeof_collection [all_outputs]] > 0} {
    set_load 0.005 [all_outputs]
}

read_vcd -strip_path $STRIP_PATH $VCD_FILE
check_timing > "$RPT_DIR/check_timing.rpt"
update_timing
update_power
report_analysis_coverage > "$RPT_DIR/analysis_coverage.rpt"
report_switching_activity > "$RPT_DIR/switching_activity.rpt"
report_switching_activity -list_not_annotated > "$RPT_DIR/not_annotated.rpt"
report_timing -delay_type max -max_paths 20 -significant_digits 8 > "$RPT_DIR/setup.rpt"
report_timing -delay_type min -max_paths 20 -significant_digits 8 > "$RPT_DIR/hold.rpt"
report_constraint -all_violators -significant_digits 6 > "$RPT_DIR/constraints.rpt"
report_power -hierarchy -verbose > "$RPT_DIR/power.rpt"
report_power > "$RPT_DIR/power_summary.rpt"
quit
