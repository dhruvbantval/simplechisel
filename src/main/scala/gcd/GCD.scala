// See README.md for license details.

package gcd

import chisel3._
// _root_ disambiguates from package chisel3.util.circt if user imports chisel3.util._
import _root_.circt.stage.ChiselStage

/**
  * Compute GCD using subtraction method.
  * Subtracts the smaller from the larger until register y is zero.
  * value in register x is then the GCD
  */
class GCD extends Module {
  val io = IO(new Bundle {
    val value1        = Input(UInt(16.W))
    val value2        = Input(UInt(16.W))
    val loadingValues = Input(Bool())
    val outputGCD     = Output(UInt(16.W))
    val outputValid   = Output(Bool())
  })

  val x  = Reg(UInt())
  val y  = Reg(UInt())

  when(x > y) { x := x - y }
    .otherwise { y := y - x }

  when(io.loadingValues) {
    x := io.value1
    y := io.value2
  }

  io.outputGCD := x
  io.outputValid := y === 0.U
}

/**
 * Generate Verilog sources and save it in file GCD.v
 */
import java.nio.file.{Files, Paths}

object GCD extends App {
  val outDirStr: String = sys.env.get("HAGENT_BUILD_DIR")
    .filter(_.nonEmpty)
    .map(dir => s"$dir/build_gcd")
    .getOrElse("./build_gcd")
  val outDir = Paths.get(outDirStr).toAbsolutePath.normalize

  // 2) Ensure the directory exists (idempotent).
  Files.createDirectories(outDir)

  // 3) Emit SystemVerilog into that directory.
  ChiselStage.emitSystemVerilogFile(
    new GCD,
    args = Array(
      "--target-dir", outDir.toString
    ),
    // "Nicest" SystemVerilog: preserve original Chisel constructs as much as possible.
    firtoolOpts = Array(
      "-O=debug",                                // minimal optimization -> modules stay close to source
      "--preserve-aggregate=all",                // keep vectors AND bundles as packed arrays / structs
      "--scalarize-public-modules=false",        // keep aggregate ports on the top/public module
      "--scalarize-ext-modules=false",           // keep aggregate ports on blackboxes too
      "--preserve-values=named",                 // keep meaningful signal names (use =all to keep everything)
      "--emit-separate-always-blocks",           // one always block per register
      "--lowering-options=disallowMuxInlining",  // Mux/when stay as their own named wires
      "-default-layer-specialization=enable",
      "-disable-all-randomization"
      // NOTE: debug info kept (no -strip-debug-info) -> // src/...scala:line locators per signal.
      // NOTE: deduplication is ON by default (don't pass --no-dedup) -> fewer Foo_1/Foo_2 copies.
    )
  )
}
