// SPDX-License-Identifier: Apache-2.0
//
// chaos_engine: deterministic chaotic-map voice engine (spine voice 5).
//
//   Three fixed-point chaotic maps, selected by `map_sel` (config 0x11 [1:0]):
//
//     map_sel = 0  LOGISTIC MAP            x <- r*x*(1-x)        (Q16 unsigned)
//     map_sel = 1  CA-PERTURBED LOGISTIC   logistic, with an 8-bit rule-30
//                                          cellular automaton XORed into the
//                                          low bits of r each update so the
//                                          chaotic trajectory drifts.
//     map_sel = 2  LORENZ                  fixed-point forward-Euler step of
//                                          the Lorenz system (x,y,z, Q12);
//                                          output coordinate = x.
//
//   Like ks_engine this is purely integer and fully deterministic. It obeys the
//   engine contract: synchronous active-low reset, state advances ONLY on a
//   1-clk `sample_tick`, and the registered signed-16 `sample` is stable between
//   ticks -- so the spine mux wires straight to it as voice 5.
//
//   The integer algorithm is pinned bit-for-bit by models/chaos_ref.py (whose
//   output models/chaos_golden.hex the testbench compares against). This RTL is
//   bit-exact to that reference. Read it before touching the math here.
//
//   Fixed-point discipline (same as ks_engine): every product is formed at full
//   width (>= 32 bits) BEFORE any shift. The logistic / CA paths work on
//   NON-NEGATIVE magnitudes (x in [0,65535], r_q16 > 0), so their shifts are
//   LOGICAL right shifts on unsigned values. The Lorenz path holds SIGNED state
//   and uses ARITHMETIC right shifts (>>>) that floor toward -inf, matching the
//   Python model's `>>` on (possibly negative) ints exactly.

`default_nettype none

module chaos_engine #(
    parameter SAMPLE_W = 16
)(
    input  wire clk,
    input  wire rst_n,                                // active low, synchronous

    input  wire sample_tick,                          // 1-clk audio-rate strobe: one map step
    input  wire [1:0] map_sel,                        // 0x11[1:0]: 0=logistic 1=CA-logistic 2=Lorenz
    input  wire [5:0] rate,                           // 0x11[7:2]: CA sub-rate (steps every `rate` ticks)
    input  wire [7:0] r_seed,                         // 0x11[15:8]: r-parameter / reset seed

    output reg signed [SAMPLE_W-1:0] sample           // registered output, held between ticks
);

    // -----------------------------------------------------------------------
    // Logistic / CA fixed-point constants (Q16: 1.0 == 65536).
    // -----------------------------------------------------------------------
    localparam [16:0] ONE_Q16 = 17'd65536;            // 1.0 in Q16 (needs 17 bits)
    localparam [15:0] X_MAX   = 16'hFFFF;             // clamp ceiling (just under 1.0)

    // CA (rule-30) constants for map_sel = 1.
    localparam integer CA_W   = 8;                    // 8-cell cellular automaton
    localparam [7:0]   CA_RULE = 8'd30;               // elementary CA rule
    localparam [7:0]   CA_INIT = 8'h01;               // nonzero CA reset pattern

    // -----------------------------------------------------------------------
    // Lorenz fixed-point constants for map_sel = 2 (state in Q12).
    //   dx = sigma*(y-x); dy = x*(rho-z)-y; dz = x*y - beta*z;  state += deriv*dt
    // -----------------------------------------------------------------------
    localparam integer LZ_Q       = 12;               // Q-format fractional bits
    localparam signed [31:0] LZ_SIGMA   = 32'sd10;    // sigma
    localparam signed [31:0] LZ_RHO     = 32'sd28;    // rho
    localparam signed [31:0] LZ_BETA_Q8 = 32'sd683;   // beta = 8/3 in Q8 (round(2.6667*256))
    localparam integer LZ_DT_SH   = 6;                // dt = 2^-6 = 1/64
    localparam integer LZ_OUT_SH  = 1;                // sample = signed16(x_q12 >>> LZ_OUT_SH)
    // Deterministic Lorenz reset state (Q12): x=2.0, y=3.0, z=15.0.
    localparam signed [31:0] LZ_X0 = 32'sd2 <<< LZ_Q;
    localparam signed [31:0] LZ_Y0 = 32'sd3 <<< LZ_Q;
    localparam signed [31:0] LZ_Z0 = 32'sd15 <<< LZ_Q;

    // -----------------------------------------------------------------------
    // State
    // -----------------------------------------------------------------------
    reg [15:0]       x;          // logistic / CA-logistic state (Q16, unsigned)
    reg [7:0]        ca;         // 8-bit cellular-automaton register
    reg [5:0]        ca_cnt;     // CA sub-rate counter
    reg signed [31:0] lx, ly, lz; // Lorenz state (Q12, signed)

    // -----------------------------------------------------------------------
    // Combinational helpers (every net explicit, no latches).
    // -----------------------------------------------------------------------
    // r mapped from r_seed into the chaotic range [3.000, 3.996] (Q16):
    //   r_q16 = (3 << 16) + (r_seed << 8)
    wire [17:0] r_q16_base = {2'b11, 16'd0} + {2'b00, r_seed, 8'd0};  // 18 bits, always > 0

    // Deterministic nonzero reset seed for x (Q16): ((r_seed<<8)|0x80), in
    // [0x0080,0xFF80] so x is strictly inside (0,1) and never sticks at 0.
    wire [15:0] x_seed = {r_seed, 8'h80};

    // One elementary CA (rule-30) step, periodic (wrap-around) boundary.
    // cell i sees neighbours (i-1,i,i+1) mod CA_W; idx = {left,cen,right}.
    function automatic [7:0] ca_step(input [7:0] s);
        integer i;
        reg [2:0] idx;
        reg left, cen, right;
        begin
            ca_step = 8'd0;
            for (i = 0; i < CA_W; i = i + 1) begin
                left  = s[(i + 1) % CA_W];      // higher-bit neighbour
                cen   = s[i];
                right = s[(i + CA_W - 1) % CA_W]; // lower-bit neighbour
                idx   = {left, cen, right};
                ca_step[i] = CA_RULE[idx];
            end
        end
    endfunction

    // ---- Logistic update (shared by map_sel 0 and 1; r supplied as input) ----
    // one_minus_x = 65536 - x  (up to 65536, 17 bits)
    // xmul        = (x * one_minus_x) >> 16   (Q16 of x*(1-x), unsigned LOGICAL shift)
    // x_next      = (r_q16 * xmul) >> 16      (Q16, unsigned LOGICAL shift), clamp [0,65535]
    // Products are formed at full (>=32-bit) width BEFORE the shift.
    function automatic [15:0] logistic_next(input [15:0] xin, input [17:0] r_q16);
        reg [16:0] one_minus_x;
        reg [33:0] xprod;      // 16 * 17 bits -> up to 33 bits
        reg [15:0] xmul;
        reg [49:0] rprod;      // 18 * 16 bits -> up to 34 bits (50 is comfortable)
        reg [33:0] xn;         // pre-clamp x_next
        begin
            one_minus_x = ONE_Q16 - {1'b0, xin};        // 17-bit
            xprod = xin * one_minus_x;                   // full width
            xmul  = xprod[31:16];                        // >> 16 (logical), keep low 16
            rprod = r_q16 * xmul;                        // full width
            xn    = rprod[33:16];                        // >> 16 (logical)
            logistic_next = (xn > {18'd0, X_MAX}) ? X_MAX : xn[15:0];  // clamp to [0,65535]
        end
    endfunction

    // Logistic sample mapping: center [0,1) Q16 -> signed16 [-1,1):
    //   sample = signed16(x_next - 32768)
    function automatic signed [15:0] logistic_sample(input [15:0] x_next);
        logistic_sample = $signed(x_next - 16'd32768);
    endfunction

    // ---- Lorenz combinational step (operates on current lx,ly,lz) ----
    // All products formed at full 64-bit width then arithmetic-shifted (>>>),
    // matching the Python model's `>>` on signed ints (floor toward -inf).
    wire signed [31:0] lz_rho_minus_z = (LZ_RHO <<< LZ_Q) - lz;        // (rho<<Q) - z, Q12
    wire signed [63:0] lz_dx = LZ_SIGMA * (ly - lx);                    // Q12
    wire signed [63:0] lz_xz = (lx * lz_rho_minus_z) >>> LZ_Q;          // x*(rho-z) back to Q12
    wire signed [63:0] lz_dy = lz_xz - ly;                             // Q12
    wire signed [63:0] lz_xy = (lx * ly) >>> LZ_Q;                      // x*y back to Q12
    wire signed [63:0] lz_bz = (LZ_BETA_Q8 * lz) >>> 8;                // beta*z back to Q12
    wire signed [63:0] lz_dz = lz_xy - lz_bz;                          // Q12
    // Euler integrate: state += (deriv >>> LZ_DT_SH).
    // Next Lorenz state (kept as explicit wires; widths trimmed to 32 bits, which
    // bounds the attractor comfortably -- |state| stays well under 2^31).
    wire signed [31:0] lx_n = lx + $signed(lz_dx[63:LZ_DT_SH]);
    wire signed [31:0] ly_n = ly + $signed(lz_dy[63:LZ_DT_SH]);
    wire signed [31:0] lz_n = lz + $signed(lz_dz[63:LZ_DT_SH]);
    // Output coordinate x scaled & wrapped to signed-16: signed16(x_q12 >>> 1).
    wire signed [15:0] lorenz_sample = $signed(lx_n[16:LZ_OUT_SH]);

    // -----------------------------------------------------------------------
    // Sequential core: synchronous posedge clk, active-low reset.
    //   reset        -> seed all map state deterministically, sample = 0.
    //   sample_tick  -> advance the selected map; register the new sample.
    //   else         -> hold all state, hold `sample`.
    // -----------------------------------------------------------------------
    reg [17:0]  r_eff;        // effective r_q16 for this step (after CA perturb)
    reg [15:0]  x_next;       // next logistic state
    reg [7:0]   ca_n;         // next CA state
    reg         do_ca;        // CA advances this tick?

    always @(posedge clk) begin
        if (!rst_n) begin
            x      <= x_seed;
            ca     <= CA_INIT;
            ca_cnt <= 6'd0;
            lx     <= LZ_X0;
            ly     <= LZ_Y0;
            lz     <= LZ_Z0;
            sample <= {SAMPLE_W{1'b0}};
        end else if (sample_tick) begin
            case (map_sel)
                2'd0: begin
                    // LOGISTIC.
                    x_next = logistic_next(x, r_q16_base);
                    x      <= x_next;
                    sample <= logistic_sample(x_next);
                end
                2'd1: begin
                    // CA-PERTURBED LOGISTIC. Advance the CA every `rate` ticks
                    // (every tick if rate == 0), then XOR the 8 CA bits into the
                    // low byte of r before the logistic update.
                    do_ca = (rate == 6'd0) || (ca_cnt >= rate);
                    if (do_ca) begin
                        ca_n   = ca_step(ca);
                        ca     <= ca_n;
                        ca_cnt <= 6'd0;
                    end else begin
                        ca_n   = ca;            // CA unchanged this tick
                        ca_cnt <= ca_cnt + 6'd1;
                    end
                    r_eff  = r_q16_base ^ {10'd0, ca_n};   // perturb low 8 bits
                    x_next = logistic_next(x, r_eff);
                    x      <= x_next;
                    sample <= logistic_sample(x_next);
                end
                default: begin
                    // LORENZ (map_sel == 2, and any unused encoding).
                    lx     <= lx_n;
                    ly     <= ly_n;
                    lz     <= lz_n;
                    sample <= lorenz_sample;
                end
            endcase
        end
        // else: idle -- hold all state, hold `sample`.
    end

endmodule

`default_nettype wire
