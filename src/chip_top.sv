// SPDX-FileCopyrightText: © 2025 Project Template Contributors
// SPDX-License-Identifier: Apache-2.0

`default_nettype none

`include "generated_defines.svh"
`include "slot_defines.svh"

`ifdef SRAM_gf180mcu_ocd_ip_sram
`define gf180mcu_xxx_ip_sram__sram512x8m8wm1 gf180mcu_ocd_ip_sram__sram512x8m8wm1
`else
`define gf180mcu_xxx_ip_sram__sram512x8m8wm1 gf180mcu_fd_ip_sram__sram512x8m8wm1
`endif

`ifdef PAD_gf180mcu_ocd_io
`define gf180mcu_xxx_io__vdd gf180mcu_ocd_io__vdd
`define gf180mcu_xxx_io__vss gf180mcu_ocd_io__vss
`define gf180mcu_xxx_io__dvdd gf180mcu_ocd_io__dvdd
`define gf180mcu_xxx_io__dvss gf180mcu_ocd_io__dvss
`define gf180mcu_xxx_io__in_s gf180mcu_ocd_io__in_s
`define gf180mcu_xxx_io__in_c gf180mcu_ocd_io__in_c
`define gf180mcu_xxx_io__bi_24t gf180mcu_ocd_io__bi_24t
`define gf180mcu_xxx_io__asig_5p0 gf180mcu_ocd_io__asig_5p0
`else
`define gf180mcu_xxx_io__vdd gf180mcu_fd_io__dvdd
`define gf180mcu_xxx_io__vss gf180mcu_fd_io__dvss
`define gf180mcu_xxx_io__dvdd gf180mcu_fd_io__dvdd
`define gf180mcu_xxx_io__dvss gf180mcu_fd_io__dvss
`define gf180mcu_xxx_io__in_s gf180mcu_fd_io__in_s
`define gf180mcu_xxx_io__in_c gf180mcu_fd_io__in_c
`define gf180mcu_xxx_io__bi_24t gf180mcu_fd_io__bi_24t
`define gf180mcu_xxx_io__asig_5p0 gf180mcu_fd_io__asig_5p0
`endif

module chip_top #(
    // Power/ground pads for I/O
    parameter NUM_DVDD_PADS = `NUM_DVDD_PADS,
    parameter NUM_DVSS_PADS = `NUM_DVSS_PADS,

    // Power/ground pads for core
    parameter NUM_VDD_PADS = `NUM_VDD_PADS,
    parameter NUM_VSS_PADS = `NUM_VSS_PADS,

    // Signal pads
    parameter NUM_INPUT_PADS = `NUM_INPUT_PADS,
    parameter NUM_BIDIR_PADS = `NUM_BIDIR_PADS,
    parameter NUM_ANALOG_PADS = `NUM_ANALOG_PADS
    )(
    `ifdef USE_POWER_PINS
    inout  wire VDD,
    inout  wire VSS,
    inout  wire DVDD,
    inout  wire DVSS,
    `endif

    inout  wire clk_PAD,
    inout  wire rst_n_PAD,
    
    inout  wire [NUM_BIDIR_PADS-1:0] bidir_PAD,
    
    inout  wire [NUM_ANALOG_PADS-1:0] analog_PAD
);

    wire clk_PAD2CORE;
    wire rst_n_PAD2CORE;
    
    wire [NUM_BIDIR_PADS-1:0] bidir_PAD2CORE;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_OE;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_CS;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_SL;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_IE;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_PU;
    wire [NUM_BIDIR_PADS-1:0] bidir_CORE2PAD_PD;

    // In the foundry pads, the I/O and
    // core voltage domains are shorted
    `ifdef USE_POWER_PINS
    `ifdef PAD_gf180mcu_fd_io
    assign VDD = DVDD;
    assign VSS = DVSS;
    `endif
    `endif

    // Power/ground pad instances
    generate
    for (genvar i=0; i<NUM_DVDD_PADS; i++) begin : dvdd_pads
        (* keep *)
        `gf180mcu_xxx_io__dvdd pad (
            `ifdef USE_POWER_PINS
            .DVDD   (DVDD),
            .DVSS   (DVSS),
            .VDD    (VDD),
            .VSS    (VSS)
            `endif
        );
    end
    for (genvar i=0; i<NUM_DVSS_PADS; i++) begin : dvss_pads
        (* keep *)
        `gf180mcu_xxx_io__dvss pad (
            `ifdef USE_POWER_PINS
            .DVDD   (DVDD),
            .DVSS   (DVSS),
            .VDD    (VDD),
            .VSS    (VSS)
            `endif
        );
    end
    for (genvar i=0; i<NUM_VDD_PADS; i++) begin : vdd_pads
        (* keep *)
        `gf180mcu_xxx_io__vdd pad (
            `ifdef USE_POWER_PINS
            .DVDD   (DVDD),
            .DVSS   (DVSS),
            .VDD    (VDD),
            .VSS    (VSS)
            `endif
        );
    end
    for (genvar i=0; i<NUM_VSS_PADS; i++) begin : vss_pads
        (* keep *)
        `gf180mcu_xxx_io__vss pad (
            `ifdef USE_POWER_PINS
            .DVDD   (DVDD),
            .DVSS   (DVSS),
            .VDD    (VDD),
            .VSS    (VSS)
            `endif
        );
    end
    endgenerate

    // Signal IO pad instances

    // Schmitt trigger
    `gf180mcu_xxx_io__in_s clk_pad (
        `ifdef USE_POWER_PINS
        .DVDD   (DVDD),
        .DVSS   (DVSS),
        .VDD    (VDD),
        .VSS    (VSS),
        `endif
    
        .Y      (clk_PAD2CORE),
        .PAD    (clk_PAD),
        
        .PU     (1'b0),
        .PD     (1'b0)
    );
    
    // Normal input
    `gf180mcu_xxx_io__in_c rst_n_pad (
        `ifdef USE_POWER_PINS
        .DVDD   (DVDD),
        .DVSS   (DVSS),
        .VDD    (VDD),
        .VSS    (VSS),
        `endif
    
        .Y      (rst_n_PAD2CORE),
        .PAD    (rst_n_PAD),
        
        .PU     (1'b0),
        .PD     (1'b0)
    );

    generate
    for (genvar i=0; i<NUM_BIDIR_PADS; i++) begin : bidir
        (* keep *)
        `gf180mcu_xxx_io__bi_24t pad (
            `ifdef USE_POWER_PINS
            .DVDD   (DVDD),
            .DVSS   (DVSS),
            .VDD    (VDD),
            .VSS    (VSS),
            `endif
        
            .A      (bidir_CORE2PAD[i]),
            .OE     (bidir_CORE2PAD_OE[i]),
            .Y      (bidir_PAD2CORE[i]),
            .PAD    (bidir_PAD[i]),
            
            .CS     (bidir_CORE2PAD_CS[i]),
            .SL     (bidir_CORE2PAD_SL[i]),
            .IE     (bidir_CORE2PAD_IE[i]),

            .PU     (bidir_CORE2PAD_PU[i]),
            .PD     (bidir_CORE2PAD_PD[i])
        );
    end
    endgenerate

    generate
    for (genvar i=0; i<NUM_ANALOG_PADS; i++) begin : analog
        (* keep *)
        `gf180mcu_xxx_io__asig_5p0 pad (
            `ifdef USE_POWER_PINS
            .DVDD   (DVDD),
            .DVSS   (DVSS),
            .VDD    (VDD),
            .VSS    (VSS),
            `endif
            .ASIG5V (analog_PAD[i])
        );
    end
    endgenerate

    // Core design

    chip_core #(
        .NUM_BIDIR_PADS  (NUM_BIDIR_PADS),
        .NUM_ANALOG_PADS (NUM_ANALOG_PADS)
    ) i_chip_core (
        `ifdef USE_POWER_PINS
        .VDD        (VDD),
        .VSS        (VSS),
        `endif
    
        .clk        (clk_PAD2CORE),
        .rst_n      (rst_n_PAD2CORE),

        .bidir_in   (bidir_PAD2CORE),
        .bidir_out  (bidir_CORE2PAD),
        .bidir_oe   (bidir_CORE2PAD_OE),
        .bidir_cs   (bidir_CORE2PAD_CS),
        .bidir_sl   (bidir_CORE2PAD_SL),
        .bidir_ie   (bidir_CORE2PAD_IE),
        .bidir_pu   (bidir_CORE2PAD_PU),
        .bidir_pd   (bidir_CORE2PAD_PD),
        
        .analog     (analog_PAD)
    );
    
    // Do not remove, necessary for tapeout
    (* keep *) gf180mcu_ws_ip__qrcode_id qrcode_id ();
    (* keep *) gf180mcu_ws_ip__shuttle_id shuttle_id ();
    (* keep *) gf180mcu_ws_ip__project_id project_id ();
    (* keep *) gf180mcu_ws_ip__marker marker ();
    
    // the doge (metal-halftone art, obstruction-only, no pins/nets).
    // Fills the whole core; see librelane/macros/macros_5v.yaml + ip/meme.
    (* keep *) meme meme_i ();

    // row-killing band blockers where the PUF branch bundles cross the
    // std-cell side strips beside the art: pdngen can't strap those rows
    // (PDN-0179). See ip/meme_puf/script/gen_blocker.py for the geometry.
    (* keep *) puf_blocker blocker_w1 ();
    (* keep *) puf_blocker blocker_w2 ();
    (* keep *) puf_blocker blocker_e5 ();
    (* keep *) puf_blocker blocker_e6 ();
    (* keep *) puf_blocker blocker_e4 ();
    (* keep *) puf_blocker blocker_e3 ();

    // --- analog-PUF NFT fingerprint (48-tap scale-up) ---
    // 48 identical passive ppolyf_u dividers (2 series resistors, 1 tap) in
    // 6 clusters of 8, hidden inside the doge's dogecoin medallions (keepouts
    // carved by ip/meme/script/carve_puf.py, geometry in ip/meme/puf_spec.json).
    // analog_PAD[0]=Vhi / analog_PAD[1]=Vlo force rails; analog_PAD[2..49] =
    // hi-Z taps (tap k = analog_PAD[k+2]). Force across the rails, meter each
    // tap: per-die poly mismatch is the unclonable fingerprint. All pad nets
    // are SPECIAL (router skips them), so every connection is pre-drawn copper
    // in the puf_routes macro (LEF PINs + M5 bond tabs -- proven in the
    // single-bank round-4 LVS). Tap->cluster map matches gen_routes_all.py.
    (* keep *) meme_puf_cluster puf_r1 (
        .HI (analog_PAD[0]), .LO (analog_PAD[1]),
        .t0 (analog_PAD[2]),  .t1 (analog_PAD[3]),  .t2 (analog_PAD[4]),  .t3 (analog_PAD[5]),
        .t4 (analog_PAD[8]),  .t5 (analog_PAD[9]),  .t6 (analog_PAD[10]), .t7 (analog_PAD[11])
    );
    (* keep *) meme_puf_cluster puf_r2 (
        .HI (analog_PAD[0]), .LO (analog_PAD[1]),
        .t0 (analog_PAD[6]),  .t1 (analog_PAD[7]),  .t2 (analog_PAD[12]), .t3 (analog_PAD[13]),
        .t4 (analog_PAD[14]), .t5 (analog_PAD[15]), .t6 (analog_PAD[16]), .t7 (analog_PAD[17])
    );
    // R3..R6 use the pre-mirrored east cell (pins east edge, placed N --
    // FN of a dummy-SIZE macro flips about the wrong box, see gen_cluster.py)
    (* keep *) meme_puf_cluster_e puf_r5 (
        .HI (analog_PAD[0]), .LO (analog_PAD[1]),
        .t0 (analog_PAD[18]), .t1 (analog_PAD[19]), .t2 (analog_PAD[20]), .t3 (analog_PAD[21]),
        .t4 (analog_PAD[22]), .t5 (analog_PAD[23]), .t6 (analog_PAD[24]), .t7 (analog_PAD[25])
    );
    (* keep *) meme_puf_cluster_e puf_r4 (
        .HI (analog_PAD[0]), .LO (analog_PAD[1]),
        .t0 (analog_PAD[26]), .t1 (analog_PAD[27]), .t2 (analog_PAD[28]), .t3 (analog_PAD[29]),
        .t4 (analog_PAD[49]), .t5 (analog_PAD[48]), .t6 (analog_PAD[47]), .t7 (analog_PAD[46])
    );
    (* keep *) meme_puf_cluster_e puf_r3 (
        .HI (analog_PAD[0]), .LO (analog_PAD[1]),
        .t0 (analog_PAD[38]), .t1 (analog_PAD[39]), .t2 (analog_PAD[40]), .t3 (analog_PAD[41]),
        .t4 (analog_PAD[42]), .t5 (analog_PAD[43]), .t6 (analog_PAD[44]), .t7 (analog_PAD[45])
    );
    (* keep *) meme_puf_cluster_e puf_r6 (
        .HI (analog_PAD[0]), .LO (analog_PAD[1]),
        .t0 (analog_PAD[30]), .t1 (analog_PAD[31]), .t2 (analog_PAD[32]), .t3 (analog_PAD[33]),
        .t4 (analog_PAD[34]), .t5 (analog_PAD[35]), .t6 (analog_PAD[36]), .t7 (analog_PAD[37])
    );

    // pad<->cluster straps: die-wide pre-drawn copper (M5 bond tabs, corridor
    // lanes, channel runs); LEF PINs so abstract extraction merges the nets.
    (* keep *) puf_routes routes_i (
        .HI (analog_PAD[0]), .LO (analog_PAD[1]),
        .t0 (analog_PAD[2]),  .t1 (analog_PAD[3]),  .t2 (analog_PAD[4]),  .t3 (analog_PAD[5]),
        .t4 (analog_PAD[6]),  .t5 (analog_PAD[7]),  .t6 (analog_PAD[8]),  .t7 (analog_PAD[9]),
        .t8 (analog_PAD[10]), .t9 (analog_PAD[11]), .t10(analog_PAD[12]), .t11(analog_PAD[13]),
        .t12(analog_PAD[14]), .t13(analog_PAD[15]), .t14(analog_PAD[16]), .t15(analog_PAD[17]),
        .t16(analog_PAD[18]), .t17(analog_PAD[19]), .t18(analog_PAD[20]), .t19(analog_PAD[21]),
        .t20(analog_PAD[22]), .t21(analog_PAD[23]), .t22(analog_PAD[24]), .t23(analog_PAD[25]),
        .t24(analog_PAD[26]), .t25(analog_PAD[27]), .t26(analog_PAD[28]), .t27(analog_PAD[29]),
        .t28(analog_PAD[30]), .t29(analog_PAD[31]), .t30(analog_PAD[32]), .t31(analog_PAD[33]),
        .t32(analog_PAD[34]), .t33(analog_PAD[35]), .t34(analog_PAD[36]), .t35(analog_PAD[37]),
        .t36(analog_PAD[38]), .t37(analog_PAD[39]), .t38(analog_PAD[40]), .t39(analog_PAD[41]),
        .t40(analog_PAD[42]), .t41(analog_PAD[43]), .t42(analog_PAD[44]), .t43(analog_PAD[45]),
        .t44(analog_PAD[46]), .t45(analog_PAD[47]), .t46(analog_PAD[48]), .t47(analog_PAD[49])
    );

endmodule

`default_nettype wire
