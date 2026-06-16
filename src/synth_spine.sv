// SPDX-License-Identifier: Apache-2.0
//
// synth_spine: the bulletproof shared backbone of the kitchen-sink synth chip.
//
//   - Generates the audio sample rate (one `sample_tick` pulse per frame).
//   - Hosts a voice-select mux: exactly one source drives the output at a time,
//     so engines never interfere (isolation = bounded blast radius).
//   - Provides a `bypass` test-ramp source: a known sawtooth that proves the
//     serializer + external DAC path is alive during bring-up, independent of
//     any real engine.
//   - Serializes the 16-bit sample as an I2S-style stream (bclk / ws / sd).
//
// Real engines (neural, chaos, SID, bytebeat, ...) bolt on later as extra mux
// inputs. A bug in any one of them stays in that one — it cannot sink the chip.

`default_nettype none

module synth_spine #(
    parameter SAMPLE_W  = 16,
    parameter BCLK_DIV  = 16,        // clk cycles per bclk half-period -> fs = clk / (64*BCLK_DIV)
    parameter RAMP_STEP = 16'sd1024, // bypass sawtooth increment per sample
    parameter SAW_INC   = 16'd2179,  // placeholder voice 1 phase increment
    parameter SQ_INC    = 16'd1303   // placeholder voice 2 phase increment
)(
    input  wire clk,
    input  wire rst_n,                 // active low

    // --- control (v0: straight from pins; SPI config comes later) ---
    input  wire [2:0] voice_sel,       // 0=bypass ramp, 1=saw, 2=square, 3=silence, 4=Karplus-Strong pluck
    input  wire       bypass_en,       // force the test ramp regardless of voice_sel

    // --- Karplus-Strong control (voice 4) ---
    input  wire       ks_pluck,        // 1-clk strobe: (re)excite the string
    input  wire [9:0] ks_period,       // delay-line length (valid 2..1023)

    // --- I2S-style serial audio output (to an external DAC) ---
    output wire i2s_bclk,
    output wire i2s_ws,
    output wire i2s_sd,

    // --- debug / bring-up taps ---
    output reg                       sample_tick,  // 1-clk pulse at each frame start
    output reg  signed [SAMPLE_W-1:0] sample_dbg,  // the sample being serialized this frame
    output wire                      heartbeat     // slow toggle: "the chip is alive"
);

    // ---------------------------------------------------------------------
    // Bit-clock generation + falling-edge strobe (our shift event)
    // ---------------------------------------------------------------------
    localparam DW = (BCLK_DIV <= 1) ? 1 : $clog2(BCLK_DIV);
    reg [DW-1:0] div_cnt;
    reg          bclk_q;
    reg          bclk_fall;           // 1-clk strobe when bclk goes 1 -> 0

    always @(posedge clk) begin
        if (!rst_n) begin
            div_cnt   <= '0;
            bclk_q    <= 1'b0;
            bclk_fall <= 1'b0;
        end else begin
            bclk_fall <= 1'b0;
            if (div_cnt == BCLK_DIV[DW-1:0] - 1'b1) begin
                div_cnt <= '0;
                bclk_q  <= ~bclk_q;
                if (bclk_q == 1'b1) bclk_fall <= 1'b1;  // about to fall
            end else begin
                div_cnt <= div_cnt + 1'b1;
            end
        end
    end

    assign i2s_bclk = bclk_q;

    // ---------------------------------------------------------------------
    // Frame / bit sequencing + MSB-first shift register
    // 32 bits per frame: [0..15] = left channel, [16..31] = right channel.
    // Mono source is duplicated to both channels.
    // ---------------------------------------------------------------------
    reg [4:0]            bit_idx;     // index of the bit currently presented
    reg signed [15:0]    shiftreg;
    reg signed [15:0]    frame_sample;

    wire [4:0] next_idx = bit_idx + 5'd1;

    always @(posedge clk) begin
        if (!rst_n) begin
            bit_idx      <= 5'd31;    // so the first shift event lands on bit 0
            shiftreg     <= '0;
            frame_sample <= '0;
            sample_dbg   <= '0;
            sample_tick  <= 1'b0;
        end else begin
            sample_tick <= 1'b0;
            if (bclk_fall) begin
                bit_idx <= next_idx;
                if (next_idx == 5'd0) begin            // start of a new frame (left bit 0)
                    frame_sample <= sample_in;
                    shiftreg     <= sample_in;
                    sample_dbg   <= sample_in;
                    sample_tick  <= 1'b1;
                end else if (next_idx == 5'd16) begin  // right channel, same mono sample
                    shiftreg <= frame_sample;
                end else begin
                    shiftreg <= {shiftreg[14:0], 1'b0}; // shift MSB out
                end
            end
        end
    end

    assign i2s_ws = bit_idx[4];        // 0 for bits 0..15, 1 for bits 16..31
    assign i2s_sd = shiftreg[15];      // MSB first

    // ---------------------------------------------------------------------
    // Sources
    // ---------------------------------------------------------------------
    // Bypass test ramp (bring-up insurance): a clean sawtooth.
    reg signed [15:0] ramp;
    always @(posedge clk) begin
        if (!rst_n)            ramp <= '0;
        else if (sample_tick)  ramp <= ramp + RAMP_STEP;
    end

    // Placeholder voice 1: phase-accumulator sawtooth.
    reg [15:0] saw_phase;
    always @(posedge clk) begin
        if (!rst_n)            saw_phase <= '0;
        else if (sample_tick)  saw_phase <= saw_phase + SAW_INC;
    end
    wire signed [15:0] osc_saw = $signed(saw_phase ^ 16'h8000); // unsigned ramp -> centered saw

    // Placeholder voice 2: phase-accumulator square.
    reg [15:0] sq_phase;
    always @(posedge clk) begin
        if (!rst_n)            sq_phase <= '0;
        else if (sample_tick)  sq_phase <= sq_phase + SQ_INC;
    end
    wire signed [15:0] osc_sq = sq_phase[15] ? 16'sh7FFF : -16'sh8000;

    // Voice 4: Karplus-Strong plucked-string engine (advances on sample_tick).
    wire signed [15:0] ks_sample;
    ks_engine u_ks (
        .clk(clk), .rst_n(rst_n),
        .sample_tick(sample_tick),
        .pluck(ks_pluck), .period(ks_period),
        .sample(ks_sample)
    );

    // ---------------------------------------------------------------------
    // Voice-select mux: ONE source reaches the output at a time.
    // ---------------------------------------------------------------------
    reg signed [15:0] sel_sample;
    always @(*) begin
        case (voice_sel)
            3'd0:    sel_sample = ramp;
            3'd1:    sel_sample = osc_saw;
            3'd2:    sel_sample = osc_sq;
            3'd4:    sel_sample = ks_sample;
            default: sel_sample = 16'sd0;   // silence
        endcase
    end

    wire signed [15:0] sample_in = bypass_en ? ramp : sel_sample;

    // ---------------------------------------------------------------------
    // Heartbeat: a slow toggle so bring-up can confirm the chip is clocking.
    // ---------------------------------------------------------------------
    reg [9:0] hb_cnt;
    always @(posedge clk) begin
        if (!rst_n)            hb_cnt <= '0;
        else if (sample_tick)  hb_cnt <= hb_cnt + 1'b1;
    end
    assign heartbeat = hb_cnt[9];

endmodule

`default_nettype wire
