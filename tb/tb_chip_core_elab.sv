// SPDX-License-Identifier: Apache-2.0
//
// tb_chip_core_elab: acceptance harness for the 1x0p5 chip_core wiring.
//
//   1. Elaborates chip_core with the real 1x0p5 pad budget (4 input pads,
//      46 bidir pads, 4 analog pads) and every port connected.
//   2. Drives a real scenario *through the pads*: a KS period + pluck on the
//      bidir input block [15:5], voice_sel=4 / bypass off on the input pads.
//   3. Asserts the bidir direction mask: the input block [15:5] is oe=0, the
//      surrounding output bits are oe=1, and bidir_ie is the exact complement
//      of bidir_oe.
//   4. Liveness smoke check: confirms i2s_bclk (bidir_out[1]) actually toggles,
//      proving the spine clocks through the core and the I2S pin is driven.
//
// A full I2S decode is NOT repeated here -- tb_synth_spine already proves the
// sample-tick -> mux -> serializer round-trip end to end.

`timescale 1ns/1ps
`default_nettype none

module tb_chip_core_elab;

    localparam NIN = 4;    // 1x0p5 input pads
    localparam NBI = 46;   // 1x0p5 bidir pads
    localparam NAN = 4;    // 1x0p5 analog pads

    // --- pad-side signals: inputs are reg, outputs are wire ---
    reg                  clk = 1'b0;
    reg                  rst_n = 1'b0;

    reg  [NIN-1:0]       input_in = '0;
    wire [NIN-1:0]       input_pu;
    wire [NIN-1:0]       input_pd;

    reg  [NBI-1:0]       bidir_in = '0;
    wire [NBI-1:0]       bidir_out;
    wire [NBI-1:0]       bidir_oe;
    wire [NBI-1:0]       bidir_cs;
    wire [NBI-1:0]       bidir_sl;
    wire [NBI-1:0]       bidir_ie;
    wire [NBI-1:0]       bidir_pu;
    wire [NBI-1:0]       bidir_pd;

    wire [NAN-1:0]       analog;

    // --- DUT: the 1x0p5-parameterised elaboration check ---
    chip_core #(
        .NUM_INPUT_PADS (NIN),
        .NUM_BIDIR_PADS (NBI),
        .NUM_ANALOG_PADS(NAN)
    ) dut (
        .clk       (clk),
        .rst_n     (rst_n),
        .input_in  (input_in),
        .input_pu  (input_pu),
        .input_pd  (input_pd),
        .bidir_in  (bidir_in),
        .bidir_out (bidir_out),
        .bidir_oe  (bidir_oe),
        .bidir_cs  (bidir_cs),
        .bidir_sl  (bidir_sl),
        .bidir_ie  (bidir_ie),
        .bidir_pu  (bidir_pu),
        .bidir_pd  (bidir_pd),
        .analog    (analog)
    );

    always #10 clk = ~clk;   // 50 MHz

    integer errors = 0;

    // --- liveness watcher: did i2s_bclk (bidir_out[1]) show both 0 and 1? ---
    reg saw_bclk_0 = 1'b0;
    reg saw_bclk_1 = 1'b0;
    always @(posedge clk) begin
        if (rst_n) begin
            if (bidir_out[1] === 1'b0) saw_bclk_0 <= 1'b1;
            if (bidir_out[1] === 1'b1) saw_bclk_1 <= 1'b1;
        end
    end

    // --- stimulus + checks ---
    initial begin
        $dumpfile("core_elab.vcd");
        $dumpvars(0, tb_chip_core_elab);

        // hold reset, then release
        repeat (8) @(posedge clk);
        rst_n = 1'b1;

        // drive a real scenario through the PADS:
        //   bidir_in[15:6] = ks_period = 16 ; bidir_in[5] = ks_pluck strobe
        //   input_in[2:0]  = voice_sel = 4   ; input_in[3] = bypass_en = 0
        bidir_in[15:6] = 10'd16;     // ks_period
        bidir_in[34]   = 1'b1;       // spi_csn idle-high (no SPI frame in flight)
        input_in       = 4'b0100;    // voice_sel=4 (KS), bypass_en=0

        @(posedge clk); bidir_in[5] = 1'b1;   // pulse ks_pluck for one clock
        @(posedge clk); bidir_in[5] = 1'b0;

        // ---- direction-mask assertions ----
        // input block [15:5] must be oe=0
        if (bidir_oe[15:5] !== 11'b0) begin
            errors = errors + 1;
            $display("FAIL: bidir_oe[15:5] = %b (expected 0 -- input block)",
                     bidir_oe[15:5]);
        end
        // low output bits [4:0] must be oe=1
        if (bidir_oe[4:0] !== 5'b11111) begin
            errors = errors + 1;
            $display("FAIL: bidir_oe[4:0] = %b (expected 1_1111 -- outputs)",
                     bidir_oe[4:0]);
        end
        // sample_dbg mirror [31:16] must be oe=1
        if (bidir_oe[31:16] !== 16'hFFFF) begin
            errors = errors + 1;
            $display("FAIL: bidir_oe[31:16] = %h (expected FFFF -- outputs)",
                     bidir_oe[31:16]);
        end
        // SPI input block {34,33,32} must be oe=0
        if (bidir_oe[34:32] !== 3'b000) begin
            errors = errors + 1;
            $display("FAIL: bidir_oe[34:32] = %b (expected 000 -- SPI in)",
                     bidir_oe[34:32]);
        end
        // SPI miso (bit 36) must be oe=1
        if (bidir_oe[36] !== 1'b1) begin
            errors = errors + 1;
            $display("FAIL: bidir_oe[36] = %b (expected 1 -- SPI miso out)",
                     bidir_oe[36]);
        end
        // ie must be the exact complement of oe across all pads
        if (bidir_ie !== ~bidir_oe) begin
            errors = errors + 1;
            $display("FAIL: bidir_ie != ~bidir_oe  (ie=%h oe=%h)",
                     bidir_ie, bidir_oe);
        end

        // ---- liveness smoke check: let the spine clock for a while ----
        repeat (4000) @(posedge clk);
        if (!(saw_bclk_0 && saw_bclk_1)) begin
            errors = errors + 1;
            $display("FAIL: i2s_bclk (bidir_out[1]) did not toggle (saw0=%b saw1=%b)",
                     saw_bclk_0, saw_bclk_1);
        end

        // ---- summary ----
        if (errors == 0) begin
            $display("ELAB OK: chip_core 1x0p5 (4/46/4) -- direction mask correct, i2s_bclk live");
        end else begin
            $display("ELAB FAIL: %0d error(s) -- see FAIL line(s) above", errors);
        end
        $finish;
    end

    // safety timeout
    initial begin
        #2_000_000;
        $display("TIMEOUT");
        $finish;
    end

endmodule

`default_nettype wire
