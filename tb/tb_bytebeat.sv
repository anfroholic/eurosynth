// SPDX-License-Identifier: Apache-2.0
//
// tb_bytebeat: self-checking testbench proving the Bytebeat RTL
// (src/bytebeat.sv) is BIT-EXACT to the independent golden oracle vector
// (models/bytebeat_golden.hex, produced by models/bytebeat_ref.py).
//
// It mirrors the golden scenario EXACTLY (docs/engines_plan.md spec item 1):
// reset -> NFORMULA blocks of BLOCK sample_ticks, block i driving formula_sel=i
// with t_inc=1, t FREE-RUNNING across block boundaries (the DUT never resets t
// between blocks). Capture the registered `sample` each tick and compare every
// captured word (signed) against gold[k]. The design is never adjusted to fit;
// only this TB's tick->capture timing is tuned so a correct DUT yields
// NSAMP checks / 0 mismatches.

`timescale 1ns/1ps
`default_nettype none

module tb_bytebeat;

    // ----- scenario constants (mirror models/bytebeat_ref.py EXACTLY) --------
    localparam NFORMULA = 4;                  // formulas exercised
    localparam BLOCK    = 64;                 // samples per formula block
    localparam NSAMP    = NFORMULA * BLOCK;   // total samples captured (256)
    localparam T_INC    = 1;                  // t increment per tick

    // ----- DUT I/O -----------------------------------------------------------
    reg  clk = 1'b0;
    reg  rst_n = 1'b0;
    reg  sample_tick = 1'b0;
    reg  [3:0] formula_sel = 4'd0;
    reg  [7:0] t_inc = 8'd0;
    wire signed [15:0] sample;

    // DEFAULT parameters: SAMPLE_W=16. Do NOT override.
    bytebeat dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_tick(sample_tick),
        .formula_sel(formula_sel),
        .t_inc(t_inc),
        .sample(sample)
    );

    // ----- clock -------------------------------------------------------------
    always #10 clk = ~clk;   // 50 MHz, 20 ns period

    // ----- the independent oracle --------------------------------------------
    // Path relative to the run cwd (repo-root /work): `iverilog ... && vvp ...`.
    reg signed [15:0] gold [0:NSAMP-1];
    initial $readmemh("models/bytebeat_golden.hex", gold);

    integer checks = 0;
    integer fails  = 0;
    integer blk;
    integer i;
    integer k;
    reg signed [15:0] got;

    // ----- stimulus + capture ------------------------------------------------
    initial begin
        $dumpfile("/tmp/bytebeat.vcd");
        $dumpvars(0, tb_bytebeat);

        // Reset: active-low for several cycles, then deassert.
        rst_n = 1'b0;
        sample_tick = 1'b0;
        formula_sel = 4'd0;
        t_inc = T_INC[7:0];                  // t_inc = 1 for the whole run
        repeat (8) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);

        // NFORMULA blocks of BLOCK ticks. formula_sel = block index; t is NOT
        // reset between blocks (the DUT only resets t on rst_n), so it runs
        // free across boundaries -- exactly like run_golden().
        //
        // Strobe + capture timing (negedge-driven, race-free), mirroring
        // tb_ks_engine: drive sample_tick (and formula_sel) transitions on the
        // NEGEDGE so they are stable across the single posedge between two
        // negedges. On that posedge the DUT registers `sample` (NBA) from the
        // CURRENT t, then advances t. By the next negedge the NBA has settled,
        // so reading `sample` there yields golden[k]. Exactly one posedge per
        // loop iteration = one sample step per capture (no double-stepping).
        k = 0;
        for (blk = 0; blk < NFORMULA; blk = blk + 1) begin
            for (i = 0; i < BLOCK; i = i + 1) begin
                @(negedge clk);
                formula_sel = blk[3:0];      // stable for the coming posedge
                sample_tick = 1'b1;
                @(negedge clk);              // exactly one posedge elapsed -> one step
                sample_tick = 1'b0;
                got = sample;                // registered sample has settled to golden[k]

                checks = checks + 1;
                if (got !== gold[k]) begin
                    fails = fails + 1;
                    $display("frame %0d (formula %0d): got %0d expected %0d",
                             k, blk, got, gold[k]);
                end
                k = k + 1;
            end
        end

        $display("==== %0d samples checked, %0d mismatches ====", checks, fails);
        if (fails == 0) $display("==== BYTEBEAT OK: every sample matched golden ====");
        else            $display("==== BYTEBEAT FAIL ====");
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
