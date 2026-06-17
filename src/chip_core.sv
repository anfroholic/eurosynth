// SPDX-License-Identifier: Apache-2.0
//
// chip_core: top of the kitchen-sink synth. For now it instantiates only the
// spine (clock/reset -> sample-tick -> voice mux -> I2S serializer, plus the
// bypass test ramp). Real engines bolt on as additional voice_sel inputs.
//
// Pin map (1x0p5 slot: 4 input pads, 46 bidir pads, 4 analog pads):
//   input_in[2:0]  -> voice_sel   (0=bypass ramp, 1=saw, 2=square, 3=silence,
//                                  4=Karplus-Strong pluck)
//   input_in[3]    -> bypass_en   (force the bring-up test ramp)
//   (all 4 input pads are used; no pulls)
//
// BIDIR pads are per-bit direction-configurable. For a given bit:
//   OUTPUT = oe=1 & ie=0 ; INPUT = oe=0 & ie=1. So ie is the complement of oe.
//
//   INPUT bits (oe=0, ie=1):
//     bidir_in[5]      -> ks_pluck     (1-clk strobe to (re)excite the string)
//     bidir_in[15:6]   -> ks_period    (10-bit delay-line length / shared pitch)
//     bidir_in[32]     -> spi_sclk     (SPI config clock)
//     bidir_in[33]     -> spi_mosi     (SPI config data in)
//     bidir_in[34]     -> spi_csn      (SPI config chip-select, active low)
//
//   OUTPUT bits (oe=1, ie=0), everything else:
//     bidir_out[0]     <- i2s_sd       (serial audio data to external DAC)
//     bidir_out[1]     <- i2s_bclk     (bit clock)
//     bidir_out[2]     <- i2s_ws       (word select / LRCK)
//     bidir_out[3]     <- heartbeat    ("chip is alive" toggle for an LED)
//     bidir_out[4]     <- sample_tick  (audio-rate frame strobe, scope tap)
//     bidir_out[31:16] <- sample_dbg   (parallel sample mirror, bring-up debug)
//     bidir_out[36]    <- spi_miso     (SPI config data out / liveness signature)
//     all other output bits drive 0.
//
// NOTE: this map assumes NUM_BIDIR_PADS >= 37 (true for 1x0p5 = 46).

`default_nettype none

module chip_core #(
    // Defaults are placeholders only; chip_top always overrides all three
    // explicitly (e.g. #(.NUM_INPUT_PADS(4),...)). Names/order are unchanged so
    // the template's instantiation still matches; -g2012 requires a default in
    // the ANSI parameter port list.
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

    // --- input pad config: no pulls ---
    assign input_pu = '0;
    assign input_pd = '0;

    // --- bidir pad direction mask ---
    // bit i is an INPUT (oe=0) for 5<=i<=15, an OUTPUT (oe=1) everywhere else.
    // The mask is purely static (a function of NUM_BIDIR_PADS only), so a
    // generate loop drives every bit unconditionally -- no latch, and (unlike a
    // constant always @(*) block) it actually elaborates to a real value.
    wire [NUM_BIDIR_PADS-1:0] oe_mask;
    genvar bi;
    generate
        for (bi = 0; bi < NUM_BIDIR_PADS; bi = bi + 1) begin : g_oe
            // input region -> 0 ; output region -> 1.
            // inputs: KS/pitch block [15:5] + SPI-in bits {32,33,34}.
            assign oe_mask[bi] = (((bi >= 5) && (bi <= 15)) ||
                                  (bi == 32) || (bi == 33) || (bi == 34))
                                 ? 1'b0 : 1'b1;
        end
    endgenerate
    assign bidir_oe = oe_mask;
    assign bidir_ie = ~bidir_oe;     // ie is the complement of oe
    assign bidir_cs = '0;
    assign bidir_sl = '0;
    assign bidir_pu = '0;
    assign bidir_pd = '0;

    // --- controls from input pads ---
    wire [2:0] voice_sel = input_in[2:0];
    wire       bypass_en = input_in[3];

    // --- Karplus-Strong / shared-pitch controls in through bidir bits [15:5] ---
    wire       ks_pluck  = bidir_in[5];
    wire [9:0] ks_period = bidir_in[15:6];

    // --- SPI config port pins: bidir bits 32/33/34 in, 36 out ---
    wire       spi_sclk  = bidir_in[32];
    wire       spi_mosi  = bidir_in[33];
    wire       spi_csn   = bidir_in[34];
    wire       spi_miso;

    // tie off genuinely-unused inputs so the tools stay quiet. Used inputs are
    // bidir_in[15:5] (KS/pitch) and bidir_in[34:32] (SPI); everything else is
    // unused as an input (bit 36 is an SPI *output* pad, so its readback is N/A).
    logic _unused;
    assign _unused = &{1'b0, bidir_in[4:0], bidir_in[31:16],
                       bidir_in[35], bidir_in[NUM_BIDIR_PADS-1:36]};

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
        .ks_pluck   (ks_pluck),
        .ks_period  (ks_period),
        .spi_sclk   (spi_sclk),
        .spi_mosi   (spi_mosi),
        .spi_csn    (spi_csn),
        .spi_miso   (spi_miso),
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
        bout[31:16]  = sample_dbg;   // 16-bit debug mirror (NUM_BIDIR_PADS >= 32)
        bout[36]     = spi_miso;     // SPI config readback (NUM_BIDIR_PADS >= 37)
    end
    assign bidir_out = bout;

endmodule

`default_nettype wire
