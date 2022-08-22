module top (
  input  wire       clk,
  input  wire       rstn
);
  `ifdef COCOTB_SIM
  initial begin
    $dumpfile ("waveforms.vcd");
    $dumpvars;
  end
  `endif
endmodule
