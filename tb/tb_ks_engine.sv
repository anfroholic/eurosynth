// SPDX-License-Identifier: Apache-2.0
//
// tb_ks_engine: self-checking testbench proving the Karplus-Strong RTL
// (src/ks_engine.sv) is BIT-EXACT to the independent golden oracle vector
// (models/ks_golden.hex, produced by models/ks_ref.py).
//
// It mirrors the golden scenario EXACTLY (docs/karplus_strong.md "Golden-vector
// test plan"): reset -> one `pluck` strobe with period = PGOLDEN = 48 -> let the
// incremental N-clk seeding complete (NO ticks during seeding) -> issue NSAMP
// `sample_tick` pulses, capturing the registered `sample` each tick, comparing
// every captured word (signed) against gold[k]. The design is never adjusted to
// fit; only this TB's tick->capture timing is tuned so a correct DUT yields
// 256 checks / 0 mismatches with the first capture == golden[0] == -7568.

`timescale 1ns/1ps
`default_nettype none

module tb_ks_engine;

    // ----- scenario constants (mirror models/ks_ref.py EXACTLY) --------------
    localparam PGOLDEN = 48;     // pluck period (delay length N) for the golden run
    localparam NSAMP   = 256;    // number of sustain steps captured

    // ----- DUT I/O -----------------------------------------------------------
    reg  clk = 1'b0;
    reg  rst_n = 1'b0;
    reg  sample_tick = 1'b0;
    reg  pluck = 1'b0;
    reg  [9:0] period = 10'd0;            // fixed 10-bit `period` port (per contract)
    wire signed [15:0] sample;

    // DEFAULT parameters: NMAX=256, DECAY_NUM=2047, DECAY_SHIFT=12,
    // LFSR_SEED=0xACE1, LFSR_POLY=0xB400, SAMPLE_W=16. Do NOT override.
    // `period` is a fixed 10-bit port regardless of NMAX (clamped internally to
    // [2, NMAX-1]); PGOLDEN=48 <= NMAX-1 so the golden vector is unchanged.
    ks_engine dut (
        .clk(clk),
        .rst_n(rst_n),
        .sample_tick(sample_tick),
        .pluck(pluck),
        .period(period),
        .sample(sample)
    );

    // ----- clock -------------------------------------------------------------
    always #10 clk = ~clk;   // 50 MHz, 20 ns period

    // ----- the independent oracle --------------------------------------------
    // Path relative to the run cwd (repo-root /work): `iverilog ... && vvp ...`.
    reg signed [15:0] gold [0:NSAMP-1];
    initial $readmemh("models/ks_golden.hex", gold);

    integer checks = 0;
    integer fails  = 0;
    integer k;
    reg signed [15:0] got;

    // ----- stimulus + capture ------------------------------------------------
    initial begin
        $dumpfile("ks_engine.vcd");
        $dumpvars(0, tb_ks_engine);

        // Reset: active-low for several cycles, then deassert.
        rst_n = 1'b0;
        sample_tick = 1'b0;
        pluck = 1'b0;
        period = PGOLDEN[9:0];           // drive period = PGOLDEN = 48
        repeat (8) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);

        // Pluck: a 1-cycle strobe. Drive strobe transitions on the NEGEDGE so the
        // value is stable and unambiguous at the posedge the DUT samples it (no
        // clock-edge race). Set high on one negedge, low on the next -> high
        // across exactly ONE posedge. The DUT writes line[0] there and seeds.
        @(negedge clk);
        pluck = 1'b1;
        @(negedge clk);
        pluck = 1'b0;

        // Wait comfortably more than PGOLDEN clocks so the incremental N-clk
        // seeding fully completes BEFORE any sample_tick is issued. (Seeding
        // takes N=48 clks; 64 is comfortable slack. The DUT ignores any tick
        // while seeding, but we keep tick low here regardless.)
        repeat (64) @(posedge clk);

        // Issue NSAMP sample_tick pulses, capturing the registered sample.
        //
        // Strobe + capture timing (negedge-driven, race-free):
        //   Drive sample_tick transitions on the NEGEDGE so it is stable across
        //   the single posedge between two negedges. On that posedge the DUT
        //   executes one sustain step and schedules `sample <= out_val` (NBA),
        //   where out_val = line[ptr] is exactly the value model.tick() returns
        //   (== golden[k]). By the next negedge the NBA has settled, so reading
        //   `sample` there yields golden[k]. Exactly one posedge per loop = one
        //   sustain step per capture (no double-stepping).
        //
        //   First tick: completed pluck/seeding left ptr=0, so out_val = line[0]
        //   = signed16(lfsr_step(LFSR_SEED)) = -7568 = golden[0] (e270).
        for (k = 0; k < NSAMP; k = k + 1) begin
            @(negedge clk);
            sample_tick = 1'b1;   // stable high for the coming posedge
            @(negedge clk);       // exactly one posedge elapsed -> one sustain step
            sample_tick = 1'b0;
            got = sample;         // registered sample has settled to golden[k]

            checks = checks + 1;
            if (got !== gold[k]) begin
                fails = fails + 1;
                $display("frame %0d: got %0d expected %0d", k, got, gold[k]);
            end
        end

        $display("==== %0d samples checked, %0d mismatches ====", checks, fails);
        if (fails == 0) $display("==== KS OK: every sample matched golden ====");
        else            $display("==== KS FAIL ====");
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
