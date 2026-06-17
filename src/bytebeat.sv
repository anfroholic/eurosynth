// SPDX-License-Identifier: Apache-2.0
//
// bytebeat: "bytebeat" one-liner voice engine (voice 6).
//
//   A free-running UNSIGNED 32-bit time counter `t` is fed through one of N
//   classic bytebeat formulas f(t); the LOW 8 BITS of f(t) are the raw 0..255
//   waveform byte. That byte is centered into signed-16 audio. On every
//   `sample_tick`, t advances by `t_inc` (treated as 1 when zero).
//
//   "Bytebeat" is just integer arithmetic on t, so this engine is trivially
//   deterministic and bit-exact -- there is no internal feedback, only the
//   running counter. It obeys the engine contract from NOTES.md: advance state
//   only on `sample_tick`, present a registered 16-bit signed `sample` that is
//   stable between ticks, one mux case -- so the spine wires straight to it.
//
//   CRITICAL bit-exactness: every intermediate operation is on a 32-bit
//   UNSIGNED value with explicit 32-bit wrap. `t` and the intermediates are
//   declared `[31:0]` so they wrap at 32 bits exactly like the Python model
//   masks with & 0xFFFFFFFF after each op. All shifts are logical (unsigned).
//   The math is pinned bit-for-bit by models/bytebeat_ref.py (whose output
//   models/bytebeat_golden.hex the testbench compares against). This RTL is
//   bit-exact to that reference. Read both before touching the math here.
//
//   Config (docs/engines_plan.md, addr 0x10):
//     formula_sel <= config[0x10][3:0]
//     t_inc       <= config[0x10][11:4]

`default_nettype none

module bytebeat #(parameter SAMPLE_W = 16) (
    input  wire clk,
    input  wire rst_n,                          // active low, synchronous

    input  wire sample_tick,                    // 1-clk audio-rate strobe: advance one sample
    input  wire [3:0] formula_sel,              // config 0x10 [3:0]: selects bytebeat formula
    input  wire [7:0] t_inc,                    // config 0x10 [11:4]: t increment (0 => treat as 1)

    output reg signed [SAMPLE_W-1:0] sample     // registered output, held between ticks
);

    // ---------------------------------------------------------------------
    // State: the free-running unsigned 32-bit time counter.
    // ---------------------------------------------------------------------
    reg [31:0] t;

    // ---------------------------------------------------------------------
    // Combinational bytebeat formulas (every intermediate a 32-bit unsigned
    // net so it WRAPS at 32 bits, exactly like the Python model masks with
    // & 0xFFFFFFFF). Shifts are logical (operands unsigned). Each expression is
    // textually parallel to models/bytebeat_ref.py.
    // ---------------------------------------------------------------------

    // 0:  t*(t>>5 | t>>8)
    wire [31:0] f0 = t * ((t >> 5) | (t >> 8));

    // 1:  ( t*(t>>5 | t>>8) ) >> (t>>16 & 7)
    //     The multiply wraps at 32 bits FIRST (f0 is 32-bit), then a variable
    //     LOGICAL right shift by (t>>16 & 7) in 0..7.
    wire [2:0]  f1_sh = (t >> 16) & 32'd7;
    wire [31:0] f1    = f0 >> f1_sh;

    // 2:  t * ( ((t>>12)|(t>>8)) & (63 & (t>>4)) )
    wire [31:0] f2_inner = ((t >> 12) | (t >> 8)) & (32'd63 & (t >> 4));
    wire [31:0] f2       = t * f2_inner;

    // 3:  t & (t>>8)
    wire [31:0] f3 = t & (t >> 8);

    // Select the active formula; any sel >= 4 maps to formula 0 (mirrors the
    // Python `formula()` fallback).
    reg [31:0] fsel;
    always @* begin
        case (formula_sel)
            4'd0:    fsel = f0;
            4'd1:    fsel = f1;
            4'd2:    fsel = f2;
            4'd3:    fsel = f3;
            default: fsel = f0;
        endcase
    end

    // Low 8 bits = the raw 0..255 bytebeat waveform byte.
    wire [7:0] byte8 = fsel[7:0];

    // Center the 0..255 byte into signed-16: (byte8 << 8) - 32768, range
    // -32768..32512. {byte8, 8'h00} is the unsigned 16-bit (byte8<<8); the
    // subtract of 0x8000 is the two's-complement re-centering (== XOR of MSB),
    // and reinterpreting the 16-bit result as signed gives the audio sample.
    wire [15:0]        centered_u = {byte8, 8'h00} - 16'h8000;
    wire signed [15:0] centered_s = $signed(centered_u);

    // Effective step: t_inc==0 is treated as 1.
    wire [31:0] step = (t_inc == 8'd0) ? 32'd1 : {24'd0, t_inc};

    // ---------------------------------------------------------------------
    // Sequential core: everything synchronous to posedge clk, active-low reset.
    //
    //   reset       -> t = 0, sample = 0.
    //   sample_tick -> sample <= signed16((byte8<<8) - 32768) for the CURRENT t,
    //                  then t <= t + step (32-bit wrap).
    //   else        -> hold all state, hold `sample`.
    //
    // The sample captured THIS tick uses the CURRENT t (before the increment),
    // exactly like model.tick(): compute byte/sample from t, THEN advance t.
    // ---------------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            t      <= 32'd0;
            sample <= {SAMPLE_W{1'b0}};
        end else if (sample_tick) begin
            sample <= centered_s;          // sample for the current t
            t      <= t + step;            // advance, 32-bit free-running wrap
        end
        // else: idle -- hold all state, hold `sample`.
    end

endmodule

`default_nettype wire
