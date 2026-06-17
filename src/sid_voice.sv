// SPDX-License-Identifier: Apache-2.0
//
// sid_voice: one phase-accumulator oscillator voice for the SID-homage engine.
//
//   A 16-bit phase accumulator advanced by `freq` on every `sample_tick`
//   (wraps naturally mod 2^16). It exposes its phase MSB and the per-tick
//   accumulator overflow (carry out of bit 15) so the parent `sid_engine` can
//   wire voices into a modulation ring (ring-mod + hard sync). A combinational
//   waveform selector turns the phase into a signed-16 sample.
//
//   This is a leaf with NO opinion about the ring topology: the parent feeds in
//   the neighbor's MSB (for ring-mod) and a `sync_now` strobe (for hard sync).
//   All arithmetic is plain integer / two's-complement, bit-exact to
//   models/sid_ref.py (class Voice). Read that model before touching the math.
//
//   Engine contract: synchronous active-low reset, state advances ONLY on
//   `sample_tick`. The waveform output is purely combinational from the
//   registered phase/lfsr, so the parent can register the mixed result.

`default_nettype none

module sid_voice #(
    parameter PHASE_W   = 16,            // phase-accumulator width (wraps mod 2^PHASE_W)
    parameter SAMPLE_W  = 16,            // waveform output width
    parameter LFSR_SEED = 16'hACE1,      // noise LFSR seed / reset state
    parameter LFSR_POLY = 16'hB400       // Galois taps: x^16 + x^14 + x^13 + x^11 + 1
)(
    input  wire clk,
    input  wire rst_n,                   // active low, synchronous

    input  wire sample_tick,             // 1-clk audio-rate strobe: advance one step
    input  wire [PHASE_W-1:0] freq,      // phase increment per tick

    input  wire [2:0] wave,              // 0=saw,1=triangle,2=pulse,3=noise
    input  wire [7:0] pw,                // pulse width: threshold on top 8 phase bits
    input  wire       ring,              // 1 => ring-mod the triangle with neighbor_msb
    input  wire       neighbor_msb,      // modulation neighbor's phase MSB (sampled pre-advance)
    input  wire       sync_now,          // 1 => hard-sync: reset accumulator to 0 this tick

    output wire       phase_msb,         // current accumulator MSB (for neighbor ring-mod)
    output wire       overflow,          // carry out of the LAST advance (for neighbor sync)
    output wire signed [SAMPLE_W-1:0] wave_out   // combinational waveform sample
);

    // ---------------------------------------------------------------------
    // State (all registered; advances only on sample_tick)
    // ---------------------------------------------------------------------
    reg [PHASE_W-1:0] phase;             // 16-bit phase accumulator
    reg [15:0]        lfsr;              // 16-bit Galois noise LFSR

    localparam [PHASE_W-1:0] PHASE_HALF = {1'b1, {(PHASE_W-1){1'b0}}};  // 0x8000

    assign phase_msb = phase[PHASE_W-1];

    // Advance: full-width sum so the carry out of bit PHASE_W-1 is visible.
    wire [PHASE_W:0] phase_sum = {1'b0, phase} + {1'b0, freq};
    wire             ovf_next  = phase_sum[PHASE_W];

    // The neighbor's hard sync triggers on THIS tick's overflow (the model
    // applies sync using the overflow each voice produces this same tick). So
    // `overflow` is the COMBINATIONAL current-tick carry, not a registered flag.
    // It depends only on this voice's own registered phase/freq (independent of
    // its own sync), so wiring it into a neighbor's sync_now forms no loop.
    assign overflow = ovf_next & sample_tick;

    // One Galois LFSR step. Identical to sid_ref.lfsr_step():
    //   lsb = s[0]; s >>= 1; if (lsb) s ^= LFSR_POLY;
    function automatic [15:0] lfsr_step(input [15:0] s);
        lfsr_step = s[0] ? ((s >> 1) ^ LFSR_POLY[15:0]) : (s >> 1);
    endfunction

    // The model registers each sample from the POST-advance (and post-sync,
    // post-LFSR-step) state. So the waveform that gets captured this tick is
    // computed from the NEXT phase / NEXT lfsr, not the currently-registered
    // ones. These are the exact values latched into the regs on this posedge.
    //   nxt_phase: phase+freq, forced to 0 by hard sync.
    //   nxt_lfsr : lfsr stepped once iff this advance overflows.
    wire [PHASE_W-1:0] nxt_phase = sync_now ? {PHASE_W{1'b0}} : phase_sum[PHASE_W-1:0];
    wire [15:0]        nxt_lfsr  = ovf_next ? lfsr_step(lfsr) : lfsr;

    // ---------------------------------------------------------------------
    // Sequential core
    //   reset       -> phase=0, lfsr=LFSR_SEED
    //   sample_tick -> phase += freq (then forced to 0 if sync_now);
    //                  step the LFSR once per overflow (clocked by carry).
    // The LFSR is clocked on the NATURAL overflow (carry from the freq add),
    // independent of sync, matching the model (advance() clocks the LFSR before
    // any sync reset is applied).
    // ---------------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            phase <= {PHASE_W{1'b0}};
            lfsr  <= LFSR_SEED;
        end else if (sample_tick) begin
            // Commit the next phase / next lfsr (computed above, incl. hard sync
            // and the once-per-overflow LFSR step).
            phase <= nxt_phase;
            lfsr  <= nxt_lfsr;
        end
        // else: hold all state (and ovf, so a stale overflow does not re-trigger).
    end

    // ---------------------------------------------------------------------
    // Combinational waveform generator.
    // Computed from the NEXT phase / NEXT lfsr (the post-advance state that gets
    // registered this tick) so the captured sample matches the model, which
    // registers each sample from its post-advance state. The ring-mod neighbor
    // MSB, however, is the neighbor's PRE-advance (currently-registered) MSB --
    // supplied by the parent from the neighbor's `phase_msb` output -- matching
    // the model's pre-advance MSB snapshot.
    // Bit-exact to sid_ref.Voice.waveform().
    // ---------------------------------------------------------------------
    // saw: signed-centered ramp  phase - 0x8000.
    wire signed [SAMPLE_W-1:0] saw_v = $signed(nxt_phase - PHASE_HALF);

    // triangle: fold about the (optionally ring-modulated) MSB sign.
    wire        tri_sign = nxt_phase[PHASE_W-1] ^ (ring & neighbor_msb);
    wire [14:0] low15    = nxt_phase[14:0];
    // sign==0 ramp up, sign==1 ramp down: XOR the low 15 bits then shift up 1.
    wire [15:0] tri_u    = {(low15 ^ {15{tri_sign}}), 1'b0};       // 16-bit unsigned triangle
    wire signed [SAMPLE_W-1:0] tri_v = $signed(tri_u - PHASE_HALF); // center about 0

    // pulse: compare the top 8 phase bits to pw.  (phase>>8) >= pw -> high.
    wire signed [SAMPLE_W-1:0] pulse_v = (nxt_phase[PHASE_W-1:8] >= pw) ? 16'sh7FFF : -16'sh8000;

    // noise: next LFSR state as a signed-16 word.
    wire signed [SAMPLE_W-1:0] noise_v = $signed(nxt_lfsr);

    assign wave_out = (wave == 3'd0) ? saw_v
                    : (wave == 3'd1) ? tri_v
                    : (wave == 3'd2) ? pulse_v
                    :                  noise_v;   // wave == 3'd3

endmodule

`default_nettype wire
