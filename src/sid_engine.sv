// SPDX-License-Identifier: Apache-2.0
//
// sid_engine: SID-homage 3-voice oscillator engine (voice 3 in the spine mux).
//
//   Three `sid_voice` phase-accumulator oscillators arranged in a modulation
//   ring, with classic-SID ring-mod and hard-sync between neighbors, summed and
//   scaled to a registered signed-16 sample. Waveforms per voice: saw /
//   triangle / pulse(+PW) / LFSR-noise (see docs/engines_plan.md spec item 3).
//
//   Ring topology: voice i is modulated by voice (i+2)%3 -- the "previous" voice
//   around the ring:  v0<-v2,  v1<-v0,  v2<-v1.
//     * ring-mod (ring_en[i]): XOR voice i's triangle fold-sign with the
//       neighbor's phase MSB (affects only the triangle waveform).
//     * hard sync (sync_en[i]): when the neighbor's accumulator overflows this
//       tick, voice i's accumulator is reset to 0.
//   The neighbor MSB used for ring-mod is the registered (pre-this-tick) phase
//   MSB, so all three voices ring-modulate off a consistent snapshot exactly as
//   the parallel reference (models/sid_ref.py SID.tick) does.
//
//   MIX: sum the three signed-16 voice outputs (18-bit signed sum) and
//   arithmetic-shift right by 2 (>>>2 floors toward -inf == Python >>2). The
//   shift keeps |sample| < 2^15 so the registered signed-16 never saturates.
//
//   Engine contract: synchronous active-low reset; state advances ONLY on
//   `sample_tick`; `sample` is registered and held stable between ticks. This
//   RTL is bit-exact to models/sid_ref.py (whose output models/sid_golden.hex
//   the testbench compares against). Read that model before touching the math.

`default_nettype none

module sid_engine #(
    parameter SAMPLE_W = 16
)(
    input  wire clk,
    input  wire rst_n,                   // active low, synchronous
    input  wire sample_tick,             // 1-clk audio-rate strobe

    input  wire [15:0] v0_freq,          // per-voice phase increments
    input  wire [15:0] v1_freq,
    input  wire [15:0] v2_freq,
    input  wire [2:0]  v0_wave,          // 0=saw,1=triangle,2=pulse,3=noise
    input  wire [2:0]  v1_wave,
    input  wire [2:0]  v2_wave,
    input  wire [7:0]  v0_pw,            // pulse width (compared to phase top-8 bits)
    input  wire [7:0]  v1_pw,
    input  wire [7:0]  v2_pw,
    input  wire [2:0]  ring_en,          // per-voice ring-mod enable (bit i => voice i)
    input  wire [2:0]  sync_en,          // per-voice hard-sync enable (bit i => voice i)

    output reg  signed [SAMPLE_W-1:0] sample   // registered output, held between ticks
);

    localparam PHASE_W = 16;             // accumulator width (wraps mod 2^16)

    // Pack the per-voice control ports into 3-element vectors so the three
    // voice instances are uniform and the ring wiring is index arithmetic.
    wire [15:0] freq [0:2];
    wire [2:0]  wave [0:2];
    wire [7:0]  pw   [0:2];
    assign freq[0] = v0_freq; assign freq[1] = v1_freq; assign freq[2] = v2_freq;
    assign wave[0] = v0_wave; assign wave[1] = v1_wave; assign wave[2] = v2_wave;
    assign pw[0]   = v0_pw;   assign pw[1]   = v1_pw;   assign pw[2]   = v2_pw;

    // Per-voice ring outputs/inputs.
    wire        v_phase_msb [0:2];       // registered phase MSB of each voice
    wire        v_overflow  [0:2];       // this-tick accumulator overflow of each voice
    wire signed [SAMPLE_W-1:0] v_out [0:2];

    // Neighbor (ring/sync source) of voice i is voice (i+2)%3: v0<-v2, v1<-v0, v2<-v1.
    // Ring-mod neighbor MSB and hard-sync strobe for each voice.
    wire nbr_msb [0:2];
    wire sync_now [0:2];
    assign nbr_msb[0]  = v_phase_msb[2];
    assign nbr_msb[1]  = v_phase_msb[0];
    assign nbr_msb[2]  = v_phase_msb[1];
    assign sync_now[0] = sync_en[0] & v_overflow[2];
    assign sync_now[1] = sync_en[1] & v_overflow[0];
    assign sync_now[2] = sync_en[2] & v_overflow[1];

    // ---------------------------------------------------------------------
    // Three voices.
    // ---------------------------------------------------------------------
    genvar gi;
    generate
        for (gi = 0; gi < 3; gi = gi + 1) begin : g_voice
            sid_voice #(
                .PHASE_W   (PHASE_W),
                .SAMPLE_W  (SAMPLE_W)
            ) u_voice (
                .clk          (clk),
                .rst_n        (rst_n),
                .sample_tick  (sample_tick),
                .freq         (freq[gi]),
                .wave         (wave[gi]),
                .pw           (pw[gi]),
                .ring         (ring_en[gi]),
                .neighbor_msb (nbr_msb[gi]),
                .sync_now     (sync_now[gi]),
                .phase_msb    (v_phase_msb[gi]),
                .overflow     (v_overflow[gi]),
                .wave_out     (v_out[gi])
            );
        end
    endgenerate

    // ---------------------------------------------------------------------
    // Mix: sum three signed-16 outputs (18-bit signed) then >>>2 (floor toward
    // -inf). Sign-extend each voice to 18 bits before summing so the add is a
    // full-width signed operation, then arithmetic-shift and store the low 16.
    // ---------------------------------------------------------------------
    wire signed [17:0] v0_ext = {{2{v_out[0][SAMPLE_W-1]}}, v_out[0]};
    wire signed [17:0] v1_ext = {{2{v_out[1][SAMPLE_W-1]}}, v_out[1]};
    wire signed [17:0] v2_ext = {{2{v_out[2][SAMPLE_W-1]}}, v_out[2]};
    wire signed [17:0] mix_sum = v0_ext + v1_ext + v2_ext;
    wire signed [17:0] mix_scaled = mix_sum >>> 2;      // arithmetic right shift
    wire signed [SAMPLE_W-1:0] mix_out = mix_scaled[SAMPLE_W-1:0];

    // ---------------------------------------------------------------------
    // Register the mixed result on each sample_tick. The voices update their
    // accumulators on the same posedge; `mix_out` is combinational from those
    // PRE-update registers, so capturing it here gives exactly the sample the
    // model registers for THIS tick (model advances, then computes outputs,
    // then registers -- but its outputs use the same snapshot the RTL latches).
    //
    // NOTE on timing: the model advances accumulators BEFORE computing the
    // waveform, so each captured sample reflects the POST-advance phase. To
    // match, the engine registers the mix one tick *after* the voices advance:
    // the voices' combinational `wave_out` reflects their just-updated phase by
    // the time `sample` is read on the next negedge -- see tb capture timing.
    // ---------------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n)
            sample <= {SAMPLE_W{1'b0}};
        else if (sample_tick)
            sample <= mix_out;
    end

endmodule

`default_nettype wire
