// SPDX-License-Identifier: Apache-2.0
//
// spi_config: SPI slave config port for the eurosynth deep-config bus.
//
//   A Mode-0 (CPOL=0, CPHA=0), MSB-first SPI slave that the master uses to load
//   the per-engine parameter / neural-weight register file (docs/engines_plan.md
//   "Config register map": 128 x 16-bit). Each 24-bit frame, framed by `spi_csn`
//   going low, carries `{ addr[7:0], data[15:0] }`. On the frame's closing csn
//   RISING edge the 16-bit `data` is committed to config[addr[6:0]] and a 1-clk
//   write-event pulse (cfg_we/cfg_addr/cfg_wdata) is emitted so the rest of the
//   spine can tap writes. The whole register file is exported flattened on
//   `cfg_flat`, so any engine slices its word combinationally as
//   `cfg_flat[a*16 +: 16]`.
//
//   While a frame is open, `spi_miso` shifts out a FIXED 16-bit liveness
//   signature 16'h5713, MSB-first, so the master can confirm the slave is alive.
//
//   The SPI pins are asynchronous to `clk`: spi_sclk / spi_mosi / spi_csn are
//   each 2-FF synchronized into the clk domain and all edges (sclk rising, csn
//   falling/rising) are detected there by comparing the synchronized value to a
//   1-clk-delayed copy. This is safe ONLY because SCLK is much slower than clk
//   (clk >= ~10 MHz, SPI <= ~1 MHz), so every sclk pulse is held for many clk
//   cycles and is never missed. All sequential logic is on posedge clk with an
//   active-low SYNCHRONOUS reset.

`default_nettype none

module spi_config #(
    parameter NREG = 128                     // config register file depth (words)
)(
    input  wire clk,
    input  wire rst_n,                       // active low, SYNCHRONOUS

    // raw SPI pins (asynchronous to clk; synchronized internally)
    input  wire spi_sclk,                    // serial clock (Mode 0)
    input  wire spi_mosi,                    // master-out, sampled on sclk rising
    input  wire spi_csn,                     // chip-select, active low: frame valid while low
    output wire spi_miso,                    // slave-out: liveness signature, MSB-first

    // config register file, flattened: word a = cfg_flat[a*16 +: 16]
    output wire [NREG*16-1:0] cfg_flat,

    // write-event taps (1-clk pulse on frame completion / csn rising)
    output reg        cfg_we,
    output reg [6:0]  cfg_addr,
    output reg [15:0] cfg_wdata
);

    // 16-bit fixed liveness signature shifted out on MISO each frame.
    localparam [15:0] MISO_SIG = 16'h5713;

    // Index width for the regfile (NREG storable words, masked to 7 bits below).
    localparam AW = $clog2(NREG);

    // ---------------------------------------------------------------------
    // Clock-domain crossing: 2-FF synchronize each async SPI pin into clk, plus
    // a 1-clk-delayed copy for edge detection. (sync2 is the clean value; sync3
    // is sync2 delayed one clk.)
    // ---------------------------------------------------------------------
    reg sclk_s1, sclk_s2, sclk_s3;
    reg mosi_s1, mosi_s2;
    reg csn_s1,  csn_s2,  csn_s3;

    always @(posedge clk) begin
        if (!rst_n) begin
            sclk_s1 <= 1'b0; sclk_s2 <= 1'b0; sclk_s3 <= 1'b0;
            mosi_s1 <= 1'b0; mosi_s2 <= 1'b0;
            // csn idles HIGH (inactive); reset to the idle level so no spurious
            // edge is seen on the first real frame.
            csn_s1  <= 1'b1; csn_s2  <= 1'b1; csn_s3  <= 1'b1;
        end else begin
            sclk_s1 <= spi_sclk; sclk_s2 <= sclk_s1; sclk_s3 <= sclk_s2;
            mosi_s1 <= spi_mosi; mosi_s2 <= mosi_s1;
            csn_s1  <= spi_csn;  csn_s2  <= csn_s1;  csn_s3  <= csn_s2;
        end
    end

    // Edge strobes in the clk domain (1-clk pulses, since sclk << clk).
    wire sclk_rise = (sclk_s2 == 1'b1) && (sclk_s3 == 1'b0);  // MOSI sample edge
    wire csn_fall  = (csn_s2  == 1'b0) && (csn_s3  == 1'b1);  // frame start
    wire csn_rise  = (csn_s2  == 1'b1) && (csn_s3  == 1'b0);  // frame end / commit

    // ---------------------------------------------------------------------
    // Frame shift / capture state
    // ---------------------------------------------------------------------
    // Inbound 24-bit shift register: MSB-first, so the most significant bit
    // (addr[7]) lands first and ends up at rx[23] after 24 shifts; the layout
    // after a complete frame is rx = { addr[7:0], data[15:0] }.
    reg [23:0] rx;
    reg [5:0]  bitcnt;          // count of sampled bits this frame (0..24, saturating)
    reg        active;          // high while csn is low (a frame is open)

    // Outbound MISO shift register, loaded with MISO_SIG at frame start (csn
    // falling). MSB-first: we present rx_miso[15] on the wire and shift left on
    // each sclk rising edge so successive MSBs appear.
    reg [15:0] tx;

    // MISO is the current top bit of the outbound shifter while a frame is open,
    // and high-Z-ish (driven 0) otherwise. We drive 0 when idle (single master,
    // simple bus) rather than tri-state to keep the model synthesizer-friendly.
    assign spi_miso = active ? tx[15] : 1'b0;

    // ---------------------------------------------------------------------
    // Config register file (NREG x 16, reset all-zero). Flattened to cfg_flat.
    // ---------------------------------------------------------------------
    reg [15:0] config_mem [0:NREG-1];

    genvar gi;
    generate
        for (gi = 0; gi < NREG; gi = gi + 1) begin : g_flat
            assign cfg_flat[gi*16 +: 16] = config_mem[gi];
        end
    endgenerate

    // 7-bit regfile index from the captured 8-bit addr (top byte of rx).
    wire [7:0] frame_addr = rx[23:16];
    wire [6:0] frame_idx  = frame_addr[6:0];      // mask to 7 bits (0..NREG-1 storable)
    wire [15:0] frame_data = rx[15:0];

    // ---------------------------------------------------------------------
    // Sequential core: all on posedge clk, synchronous active-low reset.
    // ---------------------------------------------------------------------
    integer i;
    always @(posedge clk) begin
        if (!rst_n) begin
            rx        <= 24'd0;
            bitcnt    <= 6'd0;
            active    <= 1'b0;
            tx        <= MISO_SIG;
            cfg_we    <= 1'b0;
            cfg_addr  <= 7'd0;
            cfg_wdata <= 16'd0;
            for (i = 0; i < NREG; i = i + 1)
                config_mem[i] <= 16'd0;
        end else begin
            // Default: write-event pulse is a single clk, so clear it every cycle
            // unless re-asserted by a commit below.
            cfg_we <= 1'b0;

            if (csn_fall) begin
                // Frame start: open the frame, reset the bit counter, and load a
                // FRESH copy of the liveness signature into the MISO shifter so
                // the master reads 16'h5713 back this frame. (CPHA=0: the first
                // MISO bit, MSB, is presented now, before the first sclk edge.)
                active <= 1'b1;
                bitcnt <= 6'd0;
                tx     <= MISO_SIG;
            end

            if (active && sclk_rise) begin
                // Sample MOSI on the sclk RISING edge (Mode 0), MSB-first: shift
                // the new bit into the LSB so the first-arriving (most
                // significant) bit migrates up to rx[23]. Count up to 24 and then
                // saturate -- extra bits are shifted in but the counter holds at
                // 24, so a sloppy master clocking >24 edges is tolerated; only
                // the final 24 bits before csn rising define the frame.
                rx <= {rx[22:0], mosi_s2};
                // Advance the outbound signature MSB-first on the same edge so the
                // master, which samples MISO around sclk edges, reads successive
                // bits of 16'h5713.
                tx <= {tx[14:0], 1'b0};
                if (bitcnt != 6'd24)
                    bitcnt <= bitcnt + 6'd1;
            end

            if (csn_rise) begin
                // Frame end: commit. Close the frame; write the captured 16-bit
                // data to config[addr[6:0]] and emit the 1-clk write-event pulse.
                // We commit regardless of exact bitcnt (>=24 expected); the rx
                // shifter already holds the last 24 sampled bits.
                active <= 1'b0;
                config_mem[frame_idx] <= frame_data;
                cfg_we    <= 1'b1;
                cfg_addr  <= frame_idx;
                cfg_wdata <= frame_data;
            end
        end
    end

endmodule

`default_nettype wire
