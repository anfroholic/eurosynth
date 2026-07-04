// SPDX-License-Identifier: Apache-2.0
//
// chip_core (meme edition): the entire core area is the doge art macro
// (ip/meme, instantiated in chip_top as an obstruction-only block). The only
// logic left is a free-running "wow" counter so the flow keeps a real clock
// tree, real timing paths and a non-empty netlist for LVS:
//
//   - every bidir pad is an OUTPUT (oe=1, ie=0) driving a tap of the counter,
//     so each pad toggles at clk / 2^(1 + bit index % 26);
//   - bidir_out[3] keeps the original heartbeat role (~0.4 Hz LED blink at
//     25 MHz) -- the chip is alive, much wow;
//   - input pads are unused (no pulls), analog pads untouched.
//
// rst_n stays the global synchronous init it always was (see the reset
// false_path rationale in librelane/chip_top.sdc).

`default_nettype none

module chip_core #(
    // Defaults are placeholders only; chip_top always overrides all three
    // explicitly. Names/order unchanged so the template's instantiation still
    // matches; -g2012 requires a default in the ANSI parameter port list.
    parameter NUM_INPUT_PADS  = 1,
    parameter NUM_BIDIR_PADS  = 32,
    parameter NUM_ANALOG_PADS = 1
    )(
    `ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
    `endif

    input  wire clk,
    input  wire rst_n,

    input  wire [NUM_INPUT_PADS-1:0] input_in,
    output wire [NUM_INPUT_PADS-1:0] input_pu,
    output wire [NUM_INPUT_PADS-1:0] input_pd,

    input  wire [NUM_BIDIR_PADS-1:0] bidir_in,
    output wire [NUM_BIDIR_PADS-1:0] bidir_out,
    output wire [NUM_BIDIR_PADS-1:0] bidir_oe,
    output wire [NUM_BIDIR_PADS-1:0] bidir_cs,
    output wire [NUM_BIDIR_PADS-1:0] bidir_sl,
    output wire [NUM_BIDIR_PADS-1:0] bidir_ie,
    output wire [NUM_BIDIR_PADS-1:0] bidir_pu,
    output wire [NUM_BIDIR_PADS-1:0] bidir_pd,

    inout  wire [NUM_ANALOG_PADS-1:0] analog
);

    // --- input pad config: unused, no pulls ---
    assign input_pu = '0;
    assign input_pd = '0;

    // --- the wow counter ---
    localparam WOW = 26;
    reg [WOW-1:0] wow;
    always @(posedge clk) begin
        if (!rst_n) wow <= '0;
        else        wow <= wow + 1'b1;
    end

    // --- every bidir pad is a registered counter-tap output ---
    genvar bi;
    generate
        for (bi = 0; bi < NUM_BIDIR_PADS; bi++) begin : g_out
            assign bidir_out[bi] = wow[bi % WOW];
        end
    endgenerate

    assign bidir_oe = {NUM_BIDIR_PADS{1'b1}};
    assign bidir_ie = '0;
    assign bidir_cs = '0;
    assign bidir_sl = '0;
    assign bidir_pu = '0;
    assign bidir_pd = '0;

    // consume the unused inputs (pruned at synthesis; keeps lint quiet)
    wire _unused_ok = &{1'b0, input_in, bidir_in};

endmodule

`default_nettype wire
