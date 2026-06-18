// SPDX-License-Identifier: Apache-2.0
//
// tb_spi_config: self-checking testbench for the SPI slave config port
// (src/spi_config.sv). The SPI protocol is self-defining, so this TB computes
// every expected value directly -- no external golden vector.
//
// It drives a fast clk (50 MHz) and bit-bangs the SPI pins MUCH slower (sclk
// period = 20x the clk period) so the 2-FF synchronizer + clk-domain edge
// detect in the DUT see each sclk pulse for many clk cycles, exactly as in
// silicon (clk >> sclk). The `spi_write` task drives a full Mode-0, MSB-first
// 24-bit frame ({addr[7:0], data[15:0]}) and, while doing so, reconstructs the
// 16-bit value the slave shifts out on MISO and checks it equals 16'h5713.
//
// After each frame it verifies (a) cfg_flat[addr*16 +: 16] == data and (b) the
// 1-clk write-event pulse fired with the right cfg_addr / cfg_wdata (latched by
// an always block). A mismatch counter is maintained; the run prints
// "==== <N> checks, <M> mismatches ====" and, on success,
// "==== SPI OK: config writes + miso signature verified ====".

`timescale 1ns/1ps
`default_nettype none

module tb_spi_config;

    // ----- parameters --------------------------------------------------------
    localparam NREG    = 128;
    localparam [15:0] MISO_SIG = 16'h5713;   // must match the DUT signature

    // clk = 50 MHz (20 ns). One sclk half-period spans many clk cycles so the
    // synchronizer/edge-detect works realistically. SCLK period = 800 ns (40x
    // clk period; comfortably the ">= 20x" the spec asks for).
    localparam integer SCLK_HALF = 400;      // ns, half sclk period

    // ----- DUT I/O -----------------------------------------------------------
    reg  clk = 1'b0;
    reg  rst_n = 1'b0;
    reg  spi_sclk = 1'b0;
    reg  spi_mosi = 1'b0;
    reg  spi_csn  = 1'b1;                     // idle high (inactive)
    wire spi_miso;
    wire [NREG*16-1:0] cfg_flat;
    wire        cfg_we;
    wire [6:0]  cfg_addr;
    wire [15:0] cfg_wdata;

    spi_config #(.NREG(NREG)) dut (
        .clk      (clk),
        .rst_n    (rst_n),
        .spi_sclk (spi_sclk),
        .spi_mosi (spi_mosi),
        .spi_csn  (spi_csn),
        .spi_miso (spi_miso),
        .cfg_flat (cfg_flat),
        .cfg_we   (cfg_we),
        .cfg_addr (cfg_addr),
        .cfg_wdata(cfg_wdata)
    );

    // ----- clock -------------------------------------------------------------
    always #10 clk = ~clk;                    // 50 MHz, 20 ns period

    // ----- write-event capture (latch the last write the DUT pulsed) ---------
    reg        we_seen;
    reg [6:0]  we_addr;
    reg [15:0] we_data;
    always @(posedge clk) begin
        if (!rst_n) begin
            we_seen <= 1'b0;
            we_addr <= 7'd0;
            we_data <= 16'd0;
        end else if (cfg_we) begin
            we_seen <= 1'b1;
            we_addr <= cfg_addr;
            we_data <= cfg_wdata;
        end
    end

    // ----- counters ----------------------------------------------------------
    integer checks = 0;
    integer fails  = 0;

    // ----- helpers -----------------------------------------------------------
    task do_check(input cond, input [255:0] msg);
        begin
            checks = checks + 1;
            if (!cond) begin
                fails = fails + 1;
                $display("MISMATCH: %0s", msg);
            end
        end
    endtask

    // Drive a full Mode-0 (CPOL=0, CPHA=0), MSB-first 24-bit frame and read MISO
    // back. The 24-bit payload is { addr[7:0], data[15:0] }.
    //
    // Mode 0 master timing: sclk idles low. We change MOSI while sclk is low,
    // then raise sclk (the DUT samples MOSI on this rising edge), hold, then
    // lower sclk. MISO is sampled by the master around the sclk edge; the DUT
    // presents the signature MSB at frame start and advances it on each sclk
    // rising edge, so we read MISO just before driving each rising edge -- i.e.
    // the bit the DUT has been presenting since the previous edge (or since
    // csn-fall for bit 0).
    task spi_write(input [7:0] addr, input [15:0] data);
        reg [23:0] payload;
        reg [15:0] miso_rx;
        integer b;
        begin
            payload = {addr, data};
            miso_rx = 16'd0;

            // Frame start: csn low while sclk low. Give the DUT synchronizer
            // several clk cycles to register csn falling and load the signature.
            spi_sclk = 1'b0;
            spi_csn  = 1'b0;
            #(SCLK_HALF);

            for (b = 0; b < 24; b = b + 1) begin
                // Present the next MOSI bit (MSB-first) while sclk is low.
                spi_mosi = payload[23 - b];
                #(SCLK_HALF);

                // For the first 16 bits, capture the MISO bit the DUT is
                // currently presenting (MSB-first signature). Sample right before
                // the rising edge, while it's stable.
                if (b < 16)
                    miso_rx[15 - b] = spi_miso;

                // Rising edge: DUT samples MOSI here and advances its MISO shifter.
                spi_sclk = 1'b1;
                #(SCLK_HALF);

                // Falling edge: back to idle low for the next bit.
                spi_sclk = 1'b0;
            end

            // Hold sclk low, then raise csn to end the frame -> DUT commits.
            #(SCLK_HALF);
            spi_csn = 1'b1;

            // Wait for the synchronizer to see csn rising and for the commit +
            // write-event pulse to propagate (several clk cycles).
            #(SCLK_HALF);

            // Check the reconstructed MISO signature.
            do_check(miso_rx === MISO_SIG,
                     "miso signature mismatch");
        end
    endtask

    // Verify a single address: regfile slice, write-event addr/data.
    task check_write(input [7:0] addr, input [15:0] data);
        reg [6:0] idx;
        begin
            idx = addr[6:0];
            do_check(cfg_flat[idx*16 +: 16] === data, "cfg_flat slice mismatch");
            do_check(we_seen === 1'b1,                "no write-event pulse seen");
            do_check(we_addr === idx,                 "cfg_addr mismatch");
            do_check(we_data === data,                "cfg_wdata mismatch");
        end
    endtask

    // ----- stimulus ----------------------------------------------------------
    // Distinct addresses spanning the config map (per docs/engines_plan.md) with
    // distinct data values.
    integer t;
    reg [7:0]  addrs [0:6];
    reg [15:0] datas [0:6];

    initial begin
        $dumpfile("/tmp/spi_config.vcd");
        $dumpvars(0, tb_spi_config);

        addrs[0] = 8'h00; datas[0] = 16'h0001;   // GLOBAL ctrl (config_valid)
        addrs[1] = 8'h10; datas[1] = 16'hBEEF;   // bytebeat
        addrs[2] = 8'h11; datas[2] = 16'hC0DE;   // chaos
        addrs[3] = 8'h12; datas[3] = 16'h1234;   // SID voice 0
        addrs[4] = 8'h15; datas[4] = 16'hABCD;   // neural morph
        addrs[5] = 8'h40; datas[5] = 16'h5A5A;   // neural weight (low)
        addrs[6] = 8'h4F; datas[6] = 16'hF00D;   // neural weight (high)

        // Reset: active-low synchronous, several cycles.
        rst_n = 1'b0;
        spi_csn = 1'b1;
        spi_sclk = 1'b0;
        spi_mosi = 1'b0;
        repeat (8) @(posedge clk);
        rst_n = 1'b1;
        repeat (4) @(posedge clk);

        for (t = 0; t < 7; t = t + 1) begin
            spi_write(addrs[t], datas[t]);
            repeat (4) @(posedge clk);          // let the commit settle
            check_write(addrs[t], datas[t]);
        end

        // Spot-check that an UNwritten address is still zero (regfile reset).
        do_check(cfg_flat[16'h0001*16 +: 16] === 16'h0000,
                 "untouched register not zero");

        $display("==== %0d checks, %0d mismatches ====", checks, fails);
        if (fails == 0)
            $display("==== SPI OK: config writes + miso signature verified ====");
        else
            $display("==== SPI FAIL ====");
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
