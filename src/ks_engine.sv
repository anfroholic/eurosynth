// SPDX-License-Identifier: Apache-2.0
//
// ks_engine: Karplus-Strong plucked-string voice engine.
//
//   Fill a short delay line ("the string") with a deterministic LFSR noise burst
//   on `pluck`, then circulate it through a two-tap averaging + decay filter on
//   every `sample_tick`. The noise burst is the pluck; the slowly decaying
//   recirculating signal is the ringing string.
//
//   This is the first real voice engine: tiny, purely integer, fully
//   deterministic. It obeys the engine contract from NOTES.md -- advance state
//   only on `sample_tick`, present a registered 16-bit signed `sample` that is
//   stable between ticks -- so the spine wires straight to it.
//
//   The integer algorithm and fixed-point conventions are specified in
//   docs/karplus_strong.md and pinned bit-for-bit by models/ks_ref.py (whose
//   output models/ks_golden.hex the testbench compares against). This RTL is
//   bit-exact to that reference. Read both before touching the math here.

`default_nettype none

module ks_engine #(
    parameter SAMPLE_W    = 16,
    parameter NMAX        = 256,         // delay-line depth = max period (lowest pitch)
    parameter DECAY_NUM   = 2047,        // feedback-gain numerator
    parameter DECAY_SHIFT = 12,          // gain = DECAY_NUM / 2^DECAY_SHIFT (~0.49976)
    parameter LFSR_SEED   = 16'hACE1,    // initial / reset LFSR state -> reproducible burst
    parameter LFSR_POLY   = 16'hB400     // Galois taps: x^16 + x^14 + x^13 + x^11 + 1
)(
    input  wire clk,
    input  wire rst_n,                                // active low, synchronous

    input  wire sample_tick,                          // 1-clk audio-rate strobe: sustain step
    input  wire pluck,                                // 1-clk strobe: (re)excite the string
    // `period` is a FIXED 10-bit control port (the engine contract / chip_core pin
    // map: ks_period = bidir_in[15:6]). It is clamped INTERNALLY to [2, NMAX-1], so
    // NMAX (the array depth) can change without touching the contract or the pin map.
    input  wire [9:0] period,                         // delay length N (pitch); valid 2..NMAX-1

    output reg signed [SAMPLE_W-1:0] sample           // registered output, held between ticks
);

    // ---------------------------------------------------------------------
    // State
    // ---------------------------------------------------------------------
    // The delay line ("the string"). Inferred reg-array RAM: fine for sim and
    // for proving the contract. Silicon should back this with an SRAM macro or
    // use a smaller NMAX (see docs/karplus_strong.md "AREA caveat") -- the
    // contract is independent of how `line` is stored, so that swap is later.
    reg signed [15:0] line [0:NMAX-1];

    localparam AW = $clog2(NMAX);         // index / period width

    // Feedback numerator as an explicit 32-bit signed constant, so the sustain
    // multiply below is unambiguously a full-width signed operation.
    localparam signed [31:0] DECAY_NUM_S = DECAY_NUM;

    reg [AW-1:0] ptr;                     // circular read/write pointer into line
    reg [AW-1:0] n_eff;                   // effective length N = clamp(period, 2, NMAX-1)
    reg [15:0]   lfsr;                    // 16-bit Galois LFSR state
    reg          seeding;                 // high while writing the noise burst
    reg [AW-1:0] seed_idx;                // next line[] index to seed during a pluck

    // ---------------------------------------------------------------------
    // Combinational helpers (every net declared explicitly; no latches)
    // ---------------------------------------------------------------------
    // Effective length: N = clamp(period, 2, NMAX-1), exactly as ks_ref.py clamps.
    // Captured at the moment of pluck so a mid-ring `period` change is ignored
    // until the next pluck (matches the model: N is set inside pluck()).
    //
    // `period` is a fixed 10-bit control; the array index is AW = $clog2(NMAX) bits
    // (e.g. 8 for NMAX=256). The comparison is done at full 10-bit width so a
    // `period` larger than NMAX-1 cannot wrap before it is detected; the result is
    // narrowed to AW bits ONLY on the branch where the value is provably <= NMAX-1
    // (NMAX-1 fits in AW bits by construction), so there is no truncation surprise.
    localparam [9:0]    N_MIN10 = 10'd2;             // floor: shortest string (10-bit)
    localparam [9:0]    N_MAX10 = 10'(NMAX - 1);     // ceiling: NMAX-1, fits in 10 bits
    localparam [AW-1:0] N_MIN   = AW'(2);            // floor as an AW-bit index
    localparam [AW-1:0] N_MAX   = AW'(NMAX - 1);     // ceiling as an AW-bit index
    // 10-bit clamp matching ks_ref._clamp_period EXACTLY:
    //   period < 2        -> 2
    //   period > NMAX-1   -> NMAX-1
    //   else              -> period   (now provably <= NMAX-1, so AW bits suffice)
    wire [AW-1:0] clamped_period = (period < N_MIN10) ? N_MIN
                                 : (period > N_MAX10) ? N_MAX
                                 :                      period[AW-1:0];

    // One Galois LFSR step, parameterised on the state fed in. Identical to
    // ks_ref.lfsr_step():  lsb = s[0]; s >>= 1; if (lsb) s ^= LFSR_POLY;
    function automatic [15:0] lfsr_step(input [15:0] s);
        lfsr_step = s[0] ? ((s >> 1) ^ LFSR_POLY[15:0]) : (s >> 1);
    endfunction

    // Next state of the running LFSR register.
    wire [15:0] lfsr_next = lfsr_step(lfsr);

    // First step taken from the seed, used to write line[0] on a pluck. Computing
    // it from LFSR_SEED (not the held `lfsr`) makes the pluck path independent of
    // current state, so even a pluck that arrives mid-seed restarts cleanly and
    // line[0] is always exactly signed16(lfsr_step(LFSR_SEED)) == golden's first.
    wire [15:0] lfsr_seed1 = lfsr_step(LFSR_SEED[15:0]);

    // prev index = (ptr + N - 1) mod N, for runtime-variable N. With ptr in
    // 0..N-1, this is just "ptr-1, wrapping to N-1 at zero" -- a conditional
    // decrement, no synthesis-unfriendly modulo operator.
    wire [AW-1:0] prev_idx = (ptr == {AW{1'b0}}) ? (n_eff - 1'b1) : (ptr - 1'b1);

    // next ptr = (ptr + 1) mod N: increment, wrapping to 0 at N-1.
    wire [AW-1:0] next_ptr = (ptr == n_eff - 1'b1) ? {AW{1'b0}} : (ptr + 1'b1);

    // Sustain math. Read both taps, sum, scale by the feedback gain. The product
    // is formed in a wide signed temp (>= 32-bit) BEFORE the arithmetic shift so
    // truncation floors toward -inf exactly like Python's `>>` (see spec
    // "Truncation / rounding convention"). |new| < 2^15 is proven in the spec, so
    // storing the low 16 bits wraps without ever needing saturation.
    wire signed [15:0] out_val  = line[ptr];
    wire signed [15:0] prev_val = line[prev_idx];
    // out + prev: 17-bit signed sum (|sum| <= 65535 fits with the sign bit).
    wire signed [16:0] sum2     = $signed(out_val) + $signed(prev_val);
    // Widen both operands to 32 bits BEFORE multiplying so the product is formed
    // at full width regardless of context-width resolution; max |product| is
    // 65535*2047 ~= 1.34e8 (28 bits), comfortably inside signed 32-bit.
    wire signed [31:0] acc      = $signed({{15{sum2[16]}}, sum2}) * DECAY_NUM_S;
    wire signed [31:0] scaled   = acc >>> DECAY_SHIFT;               // ARITHMETIC right shift (floor toward -inf)
    wire signed [15:0] new_val  = scaled[15:0];                      // low 16 bits, 2's-comp wrap

    // ---------------------------------------------------------------------
    // Sequential core: everything synchronous to posedge clk, active-low reset.
    //
    // Ordering / contract:
    //   * reset       -> ptr=0, lfsr=LFSR_SEED, sample=0, not seeding.
    //   * pluck strobe -> latch N, restart the LFSR from LFSR_SEED, enter seeding,
    //     write line[0] this same clk (one LFSR step then store), then one entry
    //     per clk for i=1..N-1. Completes in N clks, well before the next tick.
    //     A sample_tick arriving while seeding is ignored (sample held).
    //   * sample_tick (when not seeding) -> one sustain step; sample <= out.
    //
    // `pluck` takes priority over `sample_tick`: a tick that coincides with (or
    // arrives during) seeding is deferred, so the first post-seed tick reads
    // line[0] == the model's first captured sample == golden line 1.
    // ---------------------------------------------------------------------
    integer k;
    always @(posedge clk) begin
        if (!rst_n) begin
            // Clear the line so simulation starts from a defined (all-zero) state,
            // matching ks_ref.reset(). ptr/lfsr/sample take their reset values.
            for (k = 0; k < NMAX; k = k + 1)
                line[k] <= 16'sd0;
            ptr      <= {AW{1'b0}};
            n_eff    <= {{(AW-2){1'b0}}, 2'd2};   // matches model reset N = 2
            lfsr     <= LFSR_SEED;
            seeding  <= 1'b0;
            seed_idx <= {AW{1'b0}};
            sample   <= 16'sd0;
        end else if (pluck) begin
            // Begin a fresh noise burst. Start from LFSR_SEED, step once, and
            // write line[0] now (the model steps THEN stores, so line[0] holds the
            // post-step value). `lfsr` is loaded with that first stepped state so
            // the seeding branch continues the sequence from line[1] onward.
            n_eff      <= clamped_period;
            line[0]    <= $signed(lfsr_seed1);
            lfsr       <= lfsr_seed1;
            // Clamp floor is 2, so N >= 2 entries always get seeded (line[0] here
            // plus at least line[1] in the seeding branch).
            seed_idx   <= {{(AW-1){1'b0}}, 1'b1};  // next index to write = 1
            seeding    <= 1'b1;
            ptr        <= {AW{1'b0}};               // ptr = 0 for the first sustain read
        end else if (seeding) begin
            // Continue the burst: one write per clk, advancing the LFSR each time.
            line[seed_idx] <= $signed(lfsr_next);
            lfsr           <= lfsr_next;
            if (seed_idx == n_eff - 1'b1) begin
                // Last entry just written: burst done. Leave the loop ready to ring.
                // (Reloading lfsr to the seed here is not required for correctness --
                // the pluck path is self-contained -- but keeps the idle LFSR
                // deterministic.)
                seeding  <= 1'b0;
                lfsr     <= LFSR_SEED;
                seed_idx <= {AW{1'b0}};
                ptr      <= {AW{1'b0}};
            end else begin
                seed_idx <= seed_idx + 1'b1;
            end
            // sample held: do NOT perform a sustain step while seeding.
        end else if (sample_tick) begin
            // Sustain step (the value read THIS tick is what we output).
            //   out  = line[ptr]
            //   prev = line[(ptr+N-1) mod N]
            //   line[ptr] = (signed(out+prev) * DECAY_NUM) >>> DECAY_SHIFT   [low 16b]
            //   ptr  = (ptr+1) mod N
            //   sample <= out
            line[ptr] <= new_val;
            ptr       <= next_ptr;
            sample    <= out_val;
        end
        // else: idle -- hold all state, hold `sample`.
    end

endmodule

`default_nettype wire
