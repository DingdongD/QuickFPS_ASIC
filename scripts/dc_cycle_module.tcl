set TOP_NAME [getenv TOP_NAME]
set WORK_ROOT [getenv WORK_ROOT]
set TARGET_DB [getenv TARGET_DB]
set CLOCK_PERIOD_NS [getenv CLOCK_PERIOD_NS]
if {$CLOCK_PERIOD_NS eq ""} { set CLOCK_PERIOD_NS 1.0 }

if {$TOP_NAME eq "" || $WORK_ROOT eq "" || $TARGET_DB eq ""} {
    error "TOP_NAME, WORK_ROOT, and TARGET_DB must be set"
}

set OUT_DIR "$WORK_ROOT/build/ptpx/$TOP_NAME/dc"
set RPT_DIR "$WORK_ROOT/build/ptpx/$TOP_NAME/reports_dc"
file mkdir $OUT_DIR
file mkdir $RPT_DIR

set RTL_FILES [concat \
    [glob -nocomplain "$WORK_ROOT/RTL/bucket_engine/*.v"] \
    [glob -nocomplain "$WORK_ROOT/RTL/point_engine/*.v"] \
    [glob -nocomplain "$WORK_ROOT/RTL/memory/*.v"] \
    [glob -nocomplain "$WORK_ROOT/RTL/dma/*.v"] \
    [glob -nocomplain "$WORK_ROOT/RTL/system/*.v"] \
    [glob -nocomplain "$WORK_ROOT/RTL/top/*.v"]]

set_app_var target_library [list $TARGET_DB]
set_app_var link_library [concat "*" $target_library]
set_app_var search_path [concat [list [file dirname $TARGET_DB]] $search_path]

define_design_lib WORK -path "$OUT_DIR/work"
analyze -format verilog -library WORK $RTL_FILES
elaborate $TOP_NAME -library WORK
current_design $TOP_NAME
link
uniquify

if {[sizeof_collection [get_ports -quiet clk]] > 0} {
    create_clock -name clk -period $CLOCK_PERIOD_NS [get_ports clk]
    set_clock_uncertainty [expr {$CLOCK_PERIOD_NS * 0.05}] [get_clocks clk]
}
if {[sizeof_collection [get_ports -quiet rst_n]] > 0} {
    set_case_analysis 1 [get_ports rst_n]
    set_ideal_network -no_propagate [get_ports rst_n]
}
set data_inputs [remove_from_collection [all_inputs] [get_ports -quiet {clk rst_n}]]
if {[sizeof_collection $data_inputs] > 0} {
    set_input_delay [expr {$CLOCK_PERIOD_NS * 0.10}] -clock clk $data_inputs
    set_input_transition 0.05 $data_inputs
}
if {[sizeof_collection [all_outputs]] > 0} {
    set_output_delay [expr {$CLOCK_PERIOD_NS * 0.10}] -clock clk [all_outputs]
    set_load 0.005 [all_outputs]
}

set_max_fanout 32 [current_design]
set_max_transition [expr {$CLOCK_PERIOD_NS * 0.20}] [current_design]
compile_ultra -no_autoungroup

report_qor > "$RPT_DIR/qor.rpt"
report_area -hierarchy > "$RPT_DIR/area.rpt"
report_timing -delay_type max -max_paths 20 -significant_digits 6 > "$RPT_DIR/setup.rpt"
report_timing -delay_type min -max_paths 20 -significant_digits 6 > "$RPT_DIR/hold.rpt"
report_constraint -all_violators > "$RPT_DIR/constraints.rpt"
report_power -hierarchy > "$RPT_DIR/power_vectorless.rpt"

change_names -rules verilog -hierarchy
write -format verilog -hierarchy -output "$OUT_DIR/${TOP_NAME}_mapped.v"
write_sdc "$OUT_DIR/${TOP_NAME}.sdc"
write_sdf "$OUT_DIR/${TOP_NAME}.sdf"
write -format ddc -hierarchy -output "$OUT_DIR/${TOP_NAME}.ddc"
quit
