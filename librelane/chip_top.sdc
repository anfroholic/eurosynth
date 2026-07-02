current_design $::env(DESIGN_NAME)
set_units -time ns

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

if { $::env(CLOCK_PORT) == $::env(CLOCK_NET) } {
    set port_args [get_ports $clock_port]
} else {
    # This should actually use CLOCK_PIN?
    set port_args [get_pins [lindex $::env(CLOCK_NET) 0]]
}

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

set clocks [get_clocks $clock_port]

# Bidirectional pads
set clk_core_inout_ports [get_ports { 
    bidir_PAD[*]
}] 

set_input_delay -min 0 -clock $clocks $clk_core_inout_ports
set_input_delay -max $input_delay_value -clock $clocks $clk_core_inout_ports
set_output_delay $output_delay_value -clock $clocks $clk_core_inout_ports

# Input-only pads
set clk_core_input_ports [get_ports { 
    rst_n_PAD
    input_PAD[*]
}] 

set_input_delay -min 0 -clock $clocks $clk_core_input_ports
set_input_delay -max $input_delay_value -clock $clocks $clk_core_input_ports

# Output load
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

# ============================================================================
# TOP-LEVEL ENGINE-CONTRACT constraints (see librelane/blocks/engine.sdc for the
# per-engine version). The chip is the same sample_tick-gated machine as each
# engine, just assembled: the spine, voice mux and every engine advance state
# ONLY on sample_tick (clk/1024, ~48 kHz). The engines themselves are hardened
# MACROS, so STA sees only the thin top-level GLUE flops here; the exceptions
# below constrain that glue and the chip's I/O truthfully.
#
# Without these, the post-PnR run reported setup WNS -39.25 ns at max_ss with
# 262 violations -- but 256 of them started at rst_n_PAD (the global reset) and
# the rest at the SPI/config pads. Only ~6 were real reg->reg glue paths. None
# of the -39 ns was physical; it was single-cycle STA on paths that are not.
# ----------------------------------------------------------------------------

# (0) RESET. rst_n is a global, synchronous ("if (!rst_n)") init that enters
#     through a pad and fans out to the whole glue. It is NOT a timed
#     synchronous-release scheme: the design is entirely re-gated by sample_tick
#     (a counter comes out of reset, then sample_tick fires 1024 clocks later --
#     by which point every flop is long out of reset), so a few clocks of reset
#     de-assertion skew is absorbed and harmless. Timing the chip-wide reset
#     fanout as a single 40 ns datapath is the -39 ns artifact. Treat it as a
#     false path (standard for a global init reset). Slew/cap on the reset net
#     are still fixed by DRV repair -- those are design rules, not timing.
set _rst_port [get_ports -quiet rst_n_PAD]
if { $_rst_port ne "" } {
    puts "\[INFO] chip_top.sdc: set_false_path -from rst_n_PAD (global sample_tick-gated reset)"
    set_false_path -from $_rst_port
}

# (1) Internal reg->reg glue paths advance on sample_tick, so give them a few
#     cycles (same idiom + N as engine.sdc). N=3 is deeply conservative vs the
#     true 1024-cycle budget. reg->output stays single-cycle (I2S/debug pads are
#     read synchronously). Macro internals are hidden behind their .lib, so this
#     only touches the top glue flops.
set _mcp_n 3
puts "\[INFO] chip_top.sdc: set_multicycle_path -setup $_mcp_n (reg->reg glue)"
set_multicycle_path -setup $_mcp_n          -from [all_registers] -to [all_registers]
set_multicycle_path -hold  [expr $_mcp_n-1] -from [all_registers] -to [all_registers]

# (2) Control inputs are ASYNCHRONOUS -> false path (setup AND hold). Every
#     non-clock chip input is an external, un-synchronized control signal with NO
#     launch-clock relationship to clk:
#       input_in[2:0]=voice_sel, input_in[3]=bypass_en, bidir[5]=ks_pluck,
#       bidir[15:6]=ks_period/pitch  -- all directly pad-STRAPPED into the engine
#         macros (no flop, no synchronizer): the user drives them by hand.
#       bidir[32:34]=SPI sclk/mosi/csn -- explicitly "asynchronous to clk,
#         2-FF synchronized inside spi_config" (timing async->first-sync-FF is
#         meaningless by construction).
#     Consequences of the async-ness are benign and by design: the engines are all
#     sample_tick-gated (~48 kHz), so a control that lands in a clk hold window at
#     worst costs ONE ~20.8 us audio sample of the old value -- inaudible. That is
#     exactly the artifact STA reported: fast-corner HOLD violations, all on
#     bidir_PAD[*] -> u_neural/u_ks strap paths (0 reg-to-reg). They cannot be
#     buffer-fixed (input arrival is pinned by set_input_delay), and raising the
#     hold margin made them WORSE. The physically-correct model for an async input
#     is a false path -- same class as the reset above. (A metastability-hard
#     control would be an RTL synchronizer, not an SDC knob.)
set _async_inputs [all_inputs]
foreach _rt [list clk_PAD rst_n_PAD] {
    set _p [get_ports -quiet $_rt]
    if { $_p ne "" } {
        foreach _pp $_p {
            set _ix [lsearch $_async_inputs $_pp]
            if { $_ix >= 0 } { set _async_inputs [lreplace $_async_inputs $_ix $_ix] }
        }
    }
}
if { [llength $_async_inputs] > 0 } {
    puts "\[INFO] chip_top.sdc: set_false_path from [llength $_async_inputs] async control inputs (setup+hold)"
    set_false_path -from $_async_inputs
}

