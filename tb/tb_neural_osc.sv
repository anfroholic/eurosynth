// SPDX-License-Identifier: Apache-2.0
//
// tb_neural_osc: self-checking testbench proving src/neural_osc.sv is BIT-EXACT
// to the independent golden oracle vector models/neural_golden.hex (produced by
// models/neural_ref.py from the same models/neural_weights.hex the RTL loads).
//
// It mirrors the golden scenario EXACTLY (models/neural_ref.py): for each morph
// in MORPHS, reset the engine (restart the phase accumulator), then issue NSTEP
// sample_ticks at a fixed PITCH, capturing the registered `sample` each tick and
// comparing (signed) against gold[k]. The time-shared MLP MAC takes many clk
// cycles after each tick, so the TB waits a large, fixed inter-tick clk budget
// (CLK_BUDGET) -- far more than the worst-case FSM cycle count -- before reading.

`timescale 1ns/1ps
`default_nettype none

module tb_neural_osc;

    // ----- scenario constants (mirror models/neural_ref.py EXACTLY) ----------
    localparam integer PITCH      = 'h140;     // phase increment per tick (320)
    localparam integer NMORPH     = 5;         // number of morph values
    localparam integer NSTEP      = 51;        // samples per morph value
    localparam integer NSAMP      = NMORPH * NSTEP;   // 255 total
    localparam integer CLK_BUDGET = 1024;      // clks waited per tick (>> worst case)

    // morph sweep, matching MORPHS in neural_ref.py
    reg [7:0] morph_vals [0:NMORPH-1];
    initial begin
        morph_vals[0] = 8'd0;
        morph_vals[1] = 8'd64;
        morph_vals[2] = 8'd128;
        morph_vals[3] = 8'd192;
        morph_vals[4] = 8'd255;
    end

    // ----- DUT I/O -----------------------------------------------------------
    reg  clk = 1'b0;
    reg  rst_n = 1'b0;
    reg  sample_tick = 1'b0;
    reg  [9:0] pitch = 10'd0;
    reg  [7:0] morph = 8'd0;
    reg        w_we = 1'b0;
    reg  [5:0] w_addr = 6'd0;
    reg  [15:0] w_wdata = 16'd0;
    wire signed [15:0] sample;

    // DEFAULT parameters: the RTL $readmemh-loads models/neural_weights.hex at
    // elaboration, so the TB only drives pitch/morph/tick. Do NOT override.
    neural_osc dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_tick(sample_tick),
        .pitch(pitch),
        .morph(morph),
        .w_we(w_we),
        .w_addr(w_addr),
        .w_wdata(w_wdata),
        .sample(sample)
    );

    // ----- clock -------------------------------------------------------------
    always #10 clk = ~clk;   // 50 MHz, 20 ns period

    // ----- the independent oracle --------------------------------------------
    reg signed [15:0] gold [0:NSAMP-1];
    initial $readmemh("models/neural_golden.hex", gold);

    integer checks = 0;
    integer fails  = 0;
    integer m, s, k;
    reg signed [15:0] got;

    // ----- stimulus + capture ------------------------------------------------
    initial begin
        $dumpfile("/tmp/neural.vcd");
        $dumpvars(0, tb_neural_osc);

        pitch = PITCH[9:0];
        k = 0;

        for (m = 0; m < NMORPH; m = m + 1) begin
            // Reset for each morph segment -> phase restarts at 0 (matches the
            // ref model's nn.reset() per morph value).
            rst_n = 1'b0;
            sample_tick = 1'b0;
            morph = morph_vals[m];
            repeat (6) @(posedge clk);
            rst_n = 1'b1;
            @(posedge clk);

            for (s = 0; s < NSTEP; s = s + 1) begin
                // Drive the tick strobe on the negedge so it is stable across the
                // single posedge the DUT samples it on (race-free).
                @(negedge clk);
                sample_tick = 1'b1;
                @(negedge clk);
                sample_tick = 1'b0;

                // Wait the fixed inter-tick budget for the MLP FSM to finish.
                repeat (CLK_BUDGET) @(posedge clk);

                got = sample;
                checks = checks + 1;
                if (got !== gold[k]) begin
                    fails = fails + 1;
                    if (fails <= 20)
                        $display("frame %0d (morph=%0d step=%0d): got %0d expected %0d",
                                 k, morph_vals[m], s, got, gold[k]);
                end
                k = k + 1;
            end
        end

        $display("==== %0d samples checked, %0d mismatches ====", checks, fails);
        if (fails == 0) $display("==== NEURAL OK: every sample matched golden ====");
        else            $display("==== NEURAL FAIL ====");
        $finish;
    end

    // ----- safety timeout ----------------------------------------------------
    initial begin
        #20_000_000;
        $display("TIMEOUT");
        $finish;
    end

endmodule

`default_nettype wire
