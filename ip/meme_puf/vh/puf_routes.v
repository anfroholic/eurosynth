// puf_routes: pre-drawn pad<->PUF straps. Real copper (the PUF's current
// path) exposed as LEF pins so abstract-mode extraction sees the merge;
// ports are wired to analog_PAD[*] in chip_top.sv.
(* blackbox *)
module puf_routes (HI, t1, t2, LO);
  inout HI, t1, t2, LO;
endmodule
