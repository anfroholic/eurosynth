// SPDX-License-Identifier: Apache-2.0
//
// tb_sid_engine: self-checking testbench proving the SID-homage RTL
// (src/sid_engine.sv + src/sid_voice.sv) is BIT-EXACT to the independent golden
// oracle vector (models/sid_golden.hex, produced by models/sid_ref.py).
//
// It mirrors the golden scenario EXACTLY (sid_ref.run_golden):
//   reset -> NSAMP sample_tick pulses under a scheduled per-voice config.
//   Phase 1 (k <  SWITCH): v0 saw, v1 triangle ring-modulated by v0,
//                          v2 pulse (pw=0x80).
//   Phase 2 (k >= SWITCH): v2 -> noise, and v1 also hard-synced by v0.
// Every captured registered `sample` (signed) is compared against gold[k]. The
// design is never adjusted to fit; only this TB's tick->capture timing is tuned
// so a correct DUT yields 256 checks / 0 mismatches.

`timescale 1ns/1ps
`default_nettype none

module tb_sid_engine;

    // ----- scenario constants (mirror models/sid_ref.py EXACTLY) -------------
    localparam NSAMP  = 256;
    localparam SWITCH = 128;

    localparam [15:0] V0_FREQ = 16'h0123;
    localparam [15:0] V1_FREQ = 16'h0456;
    localparam [15:0] V2_FREQ = 16'h0789;
    localparam [7:0]  V2_PW   = 8'h80;

    localparam [2:0] WAVE_SAW   = 3'd0;
    localparam [2:0] WAVE_TRI   = 3'd1;
    localparam [2:0] WAVE_PULSE = 3'd2;
    localparam [2:0] WAVE_NOISE = 3'd3;

    // ----- DUT I/O -----------------------------------------------------------
    reg  clk = 1'b0;
    reg  rst_n = 1'b0;
    reg  sample_tick = 1'b0;

    reg  [15:0] v0_freq, v1_freq, v2_freq;
    reg  [2:0]  v0_wave, v1_wave, v2_wave;
    reg  [7:0]  v0_pw,   v1_pw,   v2_pw;
    reg  [2:0]  ring_en, sync_en;
    wire signed [15:0] sample;

    // DEFAULT parameters (SAMPLE_W=16). Do NOT override.
    sid_engine dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_tick(sample_tick),
        .v0_freq(v0_freq), .v1_freq(v1_freq), .v2_freq(v2_freq),
        .v0_wave(v0_wave), .v1_wave(v1_wave), .v2_wave(v2_wave),
        .v0_pw(v0_pw),     .v1_pw(v1_pw),     .v2_pw(v2_pw),
        .ring_en(ring_en), .sync_en(sync_en),
        .sample(sample)
    );

    // ----- clock -------------------------------------------------------------
    always #10 clk = ~clk;   // 50 MHz, 20 ns period

    // ----- the independent oracle --------------------------------------------
    reg signed [15:0] gold [0:NSAMP-1];
    initial $readmemh("models/sid_golden.hex", gold);

    integer checks = 0;
    integer fails  = 0;
    integer k;
    reg signed [15:0] got;

    // Drive the per-voice config for sample index k (combinational schedule).
    task drive_config(input integer idx);
        begin
            v0_freq = V0_FREQ; v1_freq = V1_FREQ; v2_freq = V2_FREQ;
            v0_pw   = 8'h00;   v1_pw   = 8'h00;   v2_pw   = V2_PW;
            v0_wave = WAVE_SAW;
            v1_wave = WAVE_TRI;
            if (idx < SWITCH) begin
                v2_wave = WAVE_PULSE;
                ring_en = 3'b010;     // v1 ring-modulated by neighbor v0
                sync_en = 3'b000;
            end else begin
                v2_wave = WAVE_NOISE;
                ring_en = 3'b010;     // keep ring on v1
                sync_en = 3'b010;     // also hard-sync v1 from neighbor v0
            end
        end
    endtask

    // ----- stimulus + capture ------------------------------------------------
    initial begin
        $dumpfile("/tmp/sid.vcd");
        $dumpvars(0, tb_sid_engine);

        // Reset: active-low for several cycles, then deassert.
        rst_n = 1'b0;
        sample_tick = 1'b0;
        drive_config(0);
        repeat (8) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);

        // Issue NSAMP sample_tick pulses, capturing the registered sample.
        //
        // Strobe + capture timing (negedge-driven, race-free):
        //   Drive sample_tick (and the config) on the NEGEDGE so they are stable
        //   across the single posedge between two negedges. On that posedge the
        //   DUT advances the three accumulators and registers `sample <= mix`,
        //   where mix is the waveform sum for the phase state that becomes
        //   golden[k]. Exactly one posedge per loop = one step per capture.
        for (k = 0; k < NSAMP; k = k + 1) begin
            @(negedge clk);
            drive_config(k);
            sample_tick = 1'b1;   // stable high for the coming posedge
            @(negedge clk);       // exactly one posedge elapsed -> one step
            sample_tick = 1'b0;
            got = sample;         // registered sample has settled to golden[k]

            checks = checks + 1;
            if (got !== gold[k]) begin
                fails = fails + 1;
                if (fails <= 16)
                    $display("frame %0d: got %0d expected %0d", k, got, gold[k]);
            end
        end

        $display("==== %0d samples checked, %0d mismatches ====", checks, fails);
        if (fails == 0) $display("==== SID OK: every sample matched golden ====");
        else            $display("==== SID FAIL ====");
        $finish;
    end

    // ----- safety timeout ----------------------------------------------------
    initial begin
        #5_000_000;
        $display("TIMEOUT");
        $finish;
    end

endmodule

`default_nettype wire
