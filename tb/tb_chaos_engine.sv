// SPDX-License-Identifier: Apache-2.0
//
// tb_chaos_engine: self-checking testbench proving the Chaos RTL
// (src/chaos_engine.sv) is BIT-EXACT to the independent golden oracle vector
// (models/chaos_golden.hex, produced by models/chaos_ref.py).
//
// It mirrors the golden scenario EXACTLY: three blocks, one per implemented
// `map_sel`. For each block we drive {map_sel, rate, r_seed}, pulse a 1-clk
// synchronous reset (so the DUT re-seeds its map state from the just-applied
// config, exactly as run_golden() calls ch.config() then ch.reset()), then
// issue BLK `sample_tick` pulses, capturing the registered `sample` each tick
// and comparing it against gold[k].
//
// Strobes (reset, sample_tick) are driven on the NEGEDGE so they are stable and
// unambiguous at the single posedge the DUT samples them -- no clock-edge race,
// exactly one posedge (one map step) per capture, as in tb_ks_engine.

`timescale 1ns/1ps
`default_nettype none

module tb_chaos_engine;

    // ----- scenario constants (mirror models/chaos_ref.py EXACTLY) -----------
    localparam BLK    = 85;          // samples per map block
    localparam NBLK   = 3;           // number of blocks
    localparam NSAMP  = NBLK * BLK;  // 255 total

    // Per-block config {map_sel[1:0], rate[5:0], r_seed[7:0]} -- mirror BLOCKS[].
    // block 0: logistic,    rate=0,  r_seed=0xE6
    // block 1: CA-logistic, rate=3,  r_seed=0xC4
    // block 2: lorenz,      rate=0,  r_seed=0x00
    reg [1:0] blk_map [0:NBLK-1];
    reg [5:0] blk_rate[0:NBLK-1];
    reg [7:0] blk_seed[0:NBLK-1];

    // ----- DUT I/O -----------------------------------------------------------
    reg  clk = 1'b0;
    reg  rst_n = 1'b0;
    reg  sample_tick = 1'b0;
    reg  [1:0] map_sel = 2'd0;
    reg  [5:0] rate    = 6'd0;
    reg  [7:0] r_seed  = 8'd0;
    wire signed [15:0] sample;

    // DEFAULT parameters: SAMPLE_W=16. Do NOT override.
    chaos_engine dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_tick(sample_tick),
        .map_sel(map_sel),
        .rate(rate),
        .r_seed(r_seed),
        .sample(sample)
    );

    // ----- clock -------------------------------------------------------------
    always #10 clk = ~clk;   // 50 MHz, 20 ns period

    // ----- the independent oracle --------------------------------------------
    reg signed [15:0] gold [0:NSAMP-1];
    initial $readmemh("models/chaos_golden.hex", gold);

    integer checks = 0;
    integer fails  = 0;
    integer b, k, idx;
    reg signed [15:0] got;

    // ----- stimulus + capture ------------------------------------------------
    initial begin
        $dumpfile("/tmp/chaos.vcd");
        $dumpvars(0, tb_chaos_engine);

        // Block schedule (must match BLOCKS[] in models/chaos_ref.py).
        blk_map[0] = 2'd0; blk_rate[0] = 6'd0; blk_seed[0] = 8'hE6;
        blk_map[1] = 2'd1; blk_rate[1] = 6'd3; blk_seed[1] = 8'hC4;
        blk_map[2] = 2'd2; blk_rate[2] = 6'd0; blk_seed[2] = 8'h00;

        idx = 0;
        for (b = 0; b < NBLK; b = b + 1) begin
            // Drive this block's config, then pulse a synchronous reset so the
            // DUT re-seeds its map state from {map_sel,rate,r_seed} -- matching
            // run_golden(): ch.config(...) then ch.reset().
            @(negedge clk);
            map_sel = blk_map[b];
            rate    = blk_rate[b];
            r_seed  = blk_seed[b];
            sample_tick = 1'b0;
            rst_n   = 1'b0;          // assert reset (active low)
            repeat (3) @(negedge clk);
            rst_n   = 1'b1;          // deassert -- map state now seeded
            @(negedge clk);

            // BLK sample_tick pulses; capture the registered sample each tick.
            for (k = 0; k < BLK; k = k + 1) begin
                @(negedge clk);
                sample_tick = 1'b1;   // stable high for the coming posedge
                @(negedge clk);       // exactly one posedge -> one map step
                sample_tick = 1'b0;
                got = sample;         // registered sample settled to golden[idx]

                checks = checks + 1;
                if (got !== gold[idx]) begin
                    fails = fails + 1;
                    $display("block %0d frame %0d (idx %0d): got %0d expected %0d",
                             b, k, idx, got, gold[idx]);
                end
                idx = idx + 1;
            end
        end

        $display("==== %0d samples checked, %0d mismatches ====", checks, fails);
        if (fails == 0) $display("==== CHAOS OK: every sample matched golden ====");
        else            $display("==== CHAOS FAIL ====");
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
