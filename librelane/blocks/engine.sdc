# Shared block SDC for the sound engines (chaos, ks, ... -- the "engine contract").
#
# This is LibreLane's stock base.sdc (clock, IO delays, driving cells, DRV limits,
# uncertainty/transition/derate) with ONE addition at the bottom: an engine-contract
# MULTICYCLE PATH.
#
# Why the multicycle: every engine advances its state ONLY on `sample_tick` (see
# NOTES.md / docs -- the strobe is clk/1024, ~48 kHz). Between ticks the map inputs
# (lx, ly, lz, x, ...) are stable, so the deep combinational map (multipliers, the
# Lorenz/logistic arithmetic) has ~1024 clocks to settle -- NOT one. The state FFs
# are synthesized as recirculating-mux enables (they clock every cycle but hold their
# value when sample_tick=0), so STA, with no exception, flags these paths as needing
# to close in a single 40 ns period and reports huge negative setup slack
# (chaos_engine: -12.5 ns at max_ss). That "violation" is not physical.
#
# The fix is to tell STA the truth. All *internal* register-to-register paths in an
# engine are gated by the external sample_tick, so they are multicycle; the interface
# (input port -> first reg, last reg -> output port) stays single-cycle and is NOT
# touched by an all_registers->all_registers exception. N=2 (80 ns budget) comfortably
# covers the worst map path while keeping real setup pressure on the tool for sane
# slews; the true budget is 1024 cycles, so 2 is deeply conservative.

set clock_port __VIRTUAL_CLK__
if { [info exists ::env(CLOCK_PORT)] } {
    set port_count [llength $::env(CLOCK_PORT)]

    if { $port_count == "0" } {
        puts "\[WARNING] No CLOCK_PORT found. A dummy clock will be used."
    } elseif { $port_count != "1" } {
        puts "\[WARNING] Multi-clock files are not currently supported by the base SDC file. Only the first clock will be constrained."
    }

    if { $port_count > "0" } {
        set ::clock_port [lindex $::env(CLOCK_PORT) 0]
    }
}
set port_args [get_ports $clock_port]
puts "\[INFO] Using clock $clock_port…"
create_clock {*}$port_args -name $clock_port -period $::env(CLOCK_PERIOD)

set input_delay_value [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]
set output_delay_value [expr $::env(CLOCK_PERIOD) * $::env(IO_DELAY_CONSTRAINT) / 100]
puts "\[INFO] Setting output delay to: $output_delay_value"
puts "\[INFO] Setting input delay to: $input_delay_value"

set_max_fanout $::env(MAX_FANOUT_CONSTRAINT) [current_design]
if { [info exists ::env(MAX_TRANSITION_CONSTRAINT)] } {
    set_max_transition $::env(MAX_TRANSITION_CONSTRAINT) [current_design]
}
if { [info exists ::env(MAX_CAPACITANCE_CONSTRAINT)] } {
    set_max_capacitance $::env(MAX_CAPACITANCE_CONSTRAINT) [current_design]
}

set clk_input [get_port $clock_port]
set clk_indx [lsearch [all_inputs] $clk_input]
set all_inputs_wo_clk [lreplace [all_inputs] $clk_indx $clk_indx ""]

#set rst_input [get_port resetn]
#set rst_indx [lsearch [all_inputs] $rst_input]
#set all_inputs_wo_clk_rst [lreplace $all_inputs_wo_clk $rst_indx $rst_indx ""]
set all_inputs_wo_clk_rst $all_inputs_wo_clk

# correct resetn
set clocks [get_clocks $clock_port]

set_input_delay $input_delay_value -clock $clocks $all_inputs_wo_clk_rst
set_output_delay $output_delay_value -clock $clocks [all_outputs]

if { ![info exists ::env(SYNTH_CLK_DRIVING_CELL)] } {
    set ::env(SYNTH_CLK_DRIVING_CELL) $::env(SYNTH_DRIVING_CELL)
}

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_DRIVING_CELL) "/"] 1] \
    $all_inputs_wo_clk_rst

set_driving_cell \
    -lib_cell [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 0] \
    -pin [lindex [split $::env(SYNTH_CLK_DRIVING_CELL) "/"] 1] \
    $clk_input

set cap_load [expr $::env(OUTPUT_CAP_LOAD) / 1000.0]
puts "\[INFO] Setting load to: $cap_load"
set_load $cap_load [all_outputs]

puts "\[INFO] Setting clock uncertainty to: $::env(CLOCK_UNCERTAINTY_CONSTRAINT)"
set_clock_uncertainty $::env(CLOCK_UNCERTAINTY_CONSTRAINT) $clocks

puts "\[INFO] Setting clock transition to: $::env(CLOCK_TRANSITION_CONSTRAINT)"
set_clock_transition $::env(CLOCK_TRANSITION_CONSTRAINT) $clocks

puts "\[INFO] Setting timing derate to: $::env(TIME_DERATING_CONSTRAINT)%"
set_timing_derate -early [expr 1-[expr $::env(TIME_DERATING_CONSTRAINT) / 100]]
set_timing_derate -late [expr 1+[expr $::env(TIME_DERATING_CONSTRAINT) / 100]]

if { [info exists ::env(OPENLANE_SDC_IDEAL_CLOCKS)] && $::env(OPENLANE_SDC_IDEAL_CLOCKS) } {
    unset_propagated_clock [all_clocks]
} else {
    set_propagated_clock [all_clocks]
}

# ---- engine-contract multicycle (see header) --------------------------------
# (1) Internal reg->reg map paths advance on sample_tick (clk/1024), so give them a
#     few cycles. reg->output stays single-cycle (the chip reads `sample` synchronously).
#     N=3: the TRUE budget is 1024 cycles, so 3 is still deeply conservative, but it
#     gives the deeper engines headroom -- ks_engine's map uses ~79.7 ns, so at N=2
#     (80 ns) its setup was a fragile +0.29 ns; N=3 (120 ns) decouples setup from DRV
#     repair so slew/cap fixing can't push it negative. chaos closed comfortably at
#     N=2 already; N=3 only adds margin.
set _mcp_n 3
puts "\[INFO] engine.sdc: applying set_multicycle_path -setup $_mcp_n (reg->reg) for the sample_tick-gated map"
set_multicycle_path -setup $_mcp_n         -from [all_registers] -to [all_registers]
set_multicycle_path -hold  [expr $_mcp_n-1] -from [all_registers] -to [all_registers]

# (2) Config/parameter inputs (map_sel, rate, r_seed, pitch, morph, weights, ...) are
#     quasi-static: written over the config bus, then HELD. They feed the same
#     sample_tick-gated map, so input->reg paths from them are multicycle too. Only
#     clk, rst_n and the sample_tick strobe are genuine single-cycle real-time
#     controls, so exclude just those three (same lsearch/lreplace idiom base.sdc uses
#     for clk). This clears the input->reg residual (chaos: rate[2]->reg was -1.8 ns).
set _cfg_inputs [all_inputs]
foreach _rt [list $clock_port sample_tick rst_n] {
    set _p [get_ports -quiet $_rt]
    if { $_p ne "" } {
        set _ix [lsearch $_cfg_inputs $_p]
        if { $_ix >= 0 } { set _cfg_inputs [lreplace $_cfg_inputs $_ix $_ix] }
    }
}
if { [llength $_cfg_inputs] > 0 } {
    puts "\[INFO] engine.sdc: applying set_multicycle_path -setup $_mcp_n from [llength $_cfg_inputs] config inputs"
    set_multicycle_path -setup $_mcp_n          -from $_cfg_inputs
    set_multicycle_path -hold  [expr $_mcp_n-1] -from $_cfg_inputs
}
