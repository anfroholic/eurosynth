// SPDX-License-Identifier: Apache-2.0
//
// tb_synth_spine: drive the spine, then act as an I2S *receiver* (like the DAC
// would) and check that the decoded left-channel word equals the sample the
// spine said it was sending (sample_dbg). If the round-trip matches, the
// sample-tick -> mux -> serializer path is proven end to end.

`timescale 1ns/1ps
`default_nettype none

module tb_synth_spine;

    localparam SAMPLE_W = 16;
    localparam BCLK_DIV = 2;   // tiny divider so frames fly by in sim

    reg clk = 1'b0;
    reg rst_n = 1'b0;
    reg [2:0] voice_sel = 3'd0;
    reg bypass_en = 1'b1;
    reg ks_pluck = 1'b0;
    reg [9:0] ks_period = 10'd16;

    wire i2s_bclk, i2s_ws, i2s_sd, heartbeat, sample_tick;
    wire signed [SAMPLE_W-1:0] sample_dbg;

    synth_spine #(.SAMPLE_W(SAMPLE_W), .BCLK_DIV(BCLK_DIV)) dut (
        .clk(clk), .rst_n(rst_n),
        .voice_sel(voice_sel), .bypass_en(bypass_en),
        .ks_pluck(ks_pluck), .ks_period(ks_period),
        .i2s_bclk(i2s_bclk), .i2s_ws(i2s_ws), .i2s_sd(i2s_sd),
        .sample_tick(sample_tick), .sample_dbg(sample_dbg),
        .heartbeat(heartbeat)
    );

    always #10 clk = ~clk;   // 50 MHz

    // ---- I2S receiver (mimics the external DAC) -----------------------------
    reg        bclk_d = 1'b0;
    wire       bclk_rise = i2s_bclk & ~bclk_d;
    reg signed [15:0] rx_acc = '0;
    reg        ws_seen = 1'b1;

    integer checks = 0, fails = 0;
    reg ks_nonzero = 1'b0;   // set if any KS-voice (voice_sel==4) frame decodes non-zero

    always @(posedge clk) begin
        bclk_d <= i2s_bclk;
        if (bclk_rise) begin
            if (i2s_ws == 1'b0)                     // sampling the left channel
                rx_acc <= {rx_acc[14:0], i2s_sd};   // MSB-first
        end
        // detect end of left channel (ws 0 -> 1): rx_acc now holds 16 bits
        ws_seen <= i2s_ws;
        if (ws_seen == 1'b0 && i2s_ws == 1'b1 && rst_n) begin
            checks = checks + 1;
            if (voice_sel == 3'd4 && rx_acc !== 0) ks_nonzero <= 1'b1;
            if (rx_acc === sample_dbg) begin
                $display("  frame %0d: DAC decoded %0d  (intended %0d)  OK",
                         checks, rx_acc, sample_dbg);
            end else begin
                fails = fails + 1;
                $display("  frame %0d: DAC decoded %0d  (intended %0d)  MISMATCH",
                         checks, rx_acc, sample_dbg);
            end
        end
    end

    // ---- stimulus -----------------------------------------------------------
    initial begin
        $dumpfile("spine.vcd");
        $dumpvars(0, tb_synth_spine);

        repeat (8) @(posedge clk);
        rst_n = 1'b1;

        $display("\n[1] BYPASS test ramp (bring-up insurance path):");
        bypass_en = 1'b1; voice_sel = 3'd0;
        wait_frames(6);

        $display("\n[2] Voice 1 = sawtooth oscillator (via mux):");
        bypass_en = 1'b0; voice_sel = 3'd1;
        wait_frames(6);

        $display("\n[3] Voice 2 = square oscillator (via mux):");
        voice_sel = 3'd2;
        wait_frames(6);

        $display("\n[4] Voice 3 = silence (unused engine slot):");
        voice_sel = 3'd3;
        wait_frames(4);

        $display("\n[5] Voice 4 = Karplus-Strong (pluck then select):");
        ks_period = 10'd16;
        @(posedge clk); ks_pluck = 1'b1; @(posedge clk); ks_pluck = 1'b0;
        bypass_en = 1'b0; voice_sel = 3'd4;
        wait_frames(6);
        if (!ks_nonzero) begin
            fails = fails + 1;
            $display("  [5] FAIL: KS voice produced only silence (ks_nonzero never set)");
        end else begin
            $display("  [5] OK: KS voice reached the serializer with non-zero output");
        end

        $display("\n==== %0d frames checked, %0d mismatches ====", checks, fails);
        if (fails == 0) $display("==== SPINE OK: every decoded sample matched ====\n");
        else            $display("==== SPINE FAIL ====\n");
        $finish;
    end

    // wait for N frame-start ticks
    task wait_frames(input integer n);
        integer k;
        begin
            for (k = 0; k < n; k = k + 1) @(posedge sample_tick);
        end
    endtask

    // safety timeout
    initial begin
        #2_000_000;
        $display("TIMEOUT");
        $finish;
    end

endmodule

`default_nettype wire
