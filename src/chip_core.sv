// SPDX-License-Identifier: Apache-2.0
//
// chip_core: top of the kitchen-sink synth. For now it instantiates only the
// spine (clock/reset -> sample-tick -> voice mux -> I2S serializer, plus the
// bypass test ramp). Real engines bolt on as additional voice_sel inputs.
//
// Pin map (1x1 slot: 12 input pads, 40 bidir pads, 2 analog pads):
//   input_in[2:0]  -> voice_sel   (0=bypass ramp, 1=saw, 2=square, 3=silence)
//   input_in[3]    -> bypass_en   (force the bring-up test ramp)
//   input_in[11:4] -> reserved (gates/CV/SPI later)
//
//   bidir_out[0]   <- i2s_sd      (serial audio data to external DAC)
//   bidir_out[1]   <- i2s_bclk    (bit clock)
//   bidir_out[2]   <- i2s_ws      (word select / LRCK)
//   bidir_out[3]   <- heartbeat   ("chip is alive" toggle for an LED)
//   bidir_out[4]   <- sample_tick (audio-rate frame strobe, scope tap)
//   bidir_out[31:16] <- sample_dbg (parallel sample mirror, bring-up debug)

`default_nettype none

module chip_core #(
    parameter NUM_INPUT_PADS,
    parameter NUM_BIDIR_PADS,
    parameter NUM_ANALOG_PADS
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

    // --- input pad config: no pulls ---
    assign input_pu = '0;
    assign input_pd = '0;

    // --- bidir pads: all outputs, fast CMOS ---
    assign bidir_oe = '1;
    assign bidir_cs = '0;
    assign bidir_sl = '0;
    assign bidir_ie = ~bidir_oe;
    assign bidir_pu = '0;
    assign bidir_pd = '0;

    // --- controls from input pads ---
    wire [2:0] voice_sel = input_in[2:0];
    wire       bypass_en = input_in[3];

    // tie off unused inputs so the tools don't warn
    logic _unused;
    assign _unused = &{1'b0, input_in[NUM_INPUT_PADS-1:4], &bidir_in};

    // --- the spine ---
    wire        i2s_bclk, i2s_ws, i2s_sd, heartbeat, sample_tick;
    wire signed [15:0] sample_dbg;

    synth_spine #(
        .SAMPLE_W (16),
        .BCLK_DIV (16)
    ) u_spine (
        .clk        (clk),
        .rst_n      (rst_n),
        .voice_sel  (voice_sel),
        .bypass_en  (bypass_en),
        .i2s_bclk   (i2s_bclk),
        .i2s_ws     (i2s_ws),
        .i2s_sd     (i2s_sd),
        .sample_tick(sample_tick),
        .sample_dbg (sample_dbg),
        .heartbeat  (heartbeat)
    );

    // --- drive output pads ---
    logic [NUM_BIDIR_PADS-1:0] bout;
    always @(*) begin
        bout         = '0;
        bout[0]      = i2s_sd;
        bout[1]      = i2s_bclk;
        bout[2]      = i2s_ws;
        bout[3]      = heartbeat;
        bout[4]      = sample_tick;
        bout[31:16]  = sample_dbg;   // 16-bit debug mirror (slots have >=38 bidir pads)
    end
    assign bidir_out = bout;

endmodule

`default_nettype wire
