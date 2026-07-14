// meme_puf: passive analog PUF resistor divider. Behavioural blackbox for the
// digital flow -- the terminals are analog nets tied straight to the analog pads.
(* blackbox *)
module meme_puf (A, T1, T2, B);
  inout A, T1, T2, B;
endmodule
