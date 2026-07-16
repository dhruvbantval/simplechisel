// The base abstract CPU module which declares the CoreIO of a CPU
package dinocpu

import chisel3._
// _root_ disambiguates from package chisel3.util.circt if user imports chisel3.util._
import _root_.circt.stage.ChiselStage

import dinocpu.components._
import dinocpu.components.{BaseBranchPredictor, AlwaysTakenPredictor, AlwaysNotTakenPredictor, LocalPredictor, GlobalHistoryPredictor}
import dinocpu.memory._

import java.nio.file.{Files, Paths}

/**
  * Base CPU module which all CPU models implement
  */
abstract class BaseCPU extends Module {
  val io = IO(new CoreIO())

  // Required so the compiler doesn't optimize things away when testing
  // incomplete designs.
  dontTouch(io)
}

// Configurations for the dinocpu
// For file length
import java.io.File

/**
 * This class configures all of the dinocpus. It takes parameters for the type of CPU model
 * (e.g., single-cycle, five-cycle, etc.), and the memories to hook up.
 */
class CPUConfig
{
  /** The type of CPU to elaborate */
  var cpuType = "single-cycle"

  /** The type of branch predictor to use */
  var branchPredictor = "always-not-taken"
  /** Number of bits for the saturating counters */
  var saturatingCounterBits = 2
  /** Number of entries in the branch predictor table */
  var branchPredTableEntries = 32

  /** The memory file location */
  var memFile = "test"
  /** The noncombinational memory latency */
  var memLatency = 5
  /** The port types **/
  var memPortType = "combinational-port"
  /** The backing memory type */
  var memType = "combinational"

  def printConfig(): Unit = {
    println(s"CPU Type: ${cpuType}")
    println(s"Branch predictor: ${branchPredictor}")
    println(s"Memory file: ${memFile}")
    println(s"Memory type: ${memType}")
    println(s"Memory port type: ${memPortType}")
    println(s"Memory latency (ignored if combinational): ${memLatency}")
  }

  /**
   * Returns the CPU that we will be elaborating
   *
   * @return A CPU to elaborate.
   */

  def getBranchPredictor: BaseBranchPredictor = {
    implicit val conf = this
    branchPredictor match {
      case "always-taken"     => new AlwaysTakenPredictor
      case "always-not-taken" => new AlwaysNotTakenPredictor
      case "local"            => new LocalPredictor
      case "global"           => new GlobalHistoryPredictor
      case _ => throw new IllegalArgumentException("Must specify known branch predictor")
    }
  }

  /**
    * Create a memory with data from a file
    *
    * @param minSize is the minimum size for the memory. If the binary file is
    *        smaller than this, create a memory that is this size.
    * @return [[BaseDualPortedMemory]] object
    */
  def getNewMem(minSize: Int = 1 << 16): BaseDualPortedMemory = {
    val f = new File(memFile)
    if (f.length == 0) {
      println("WARNING: No file will be loaded for data memory")
    }

    memType match {
      case "combinational"     => new DualPortedCombinMemory (minSize, memFile)
      case "non-combinational" => new DualPortedNonCombinMemory (minSize, memFile, memLatency)
      case _ => throw new IllegalArgumentException("Must specify known backing memory type")
    }
  }

  /**
    * Create an instruction memory port
    *
    * @return [[BaseIMemPort]] object
    */
  def getIMemPort(): BaseIMemPort = {
    val f = new File(memFile)
    if (f.length == 0) {
      println("WARNING: No file will be loaded for data memory")
    }

    memPortType match {
      case "combinational-port"     => new ICombinMemPort
      case "non-combinational-port" => new INonCombinMemPort
      // case "non-combinational-cache" => new ICache
      case _ => throw new IllegalArgumentException("Must specify known instruction memory port type")
    }
  }

  /**
    * Create a data memory port
    *
    * @return [[BaseDMemPort]] object
    */
  def getDMemPort(): BaseDMemPort = {
    val f = new File(memFile)
    if (f.length == 0) {
      println("WARNING: No file will be loaded for data memory")
    }

    memPortType match {
      case "combinational-port"     => new DCombinMemPort
      case "non-combinational-port" => new DNonCombinMemPort
      // case "non-combinational-cache" => new DCache
      case _ => throw new IllegalArgumentException("Must specify known data memory port type")
    }
  }
}

// This file is where all of the CPU components are assembled into the whole CPU


import chisel3._
import chisel3.util._
import dinocpu.components._

/**
 * The main CPU definition that hooks up all of the other components.
 *
 * For more information, see section 4.4 of Patterson and Hennessy
 * This follows figure 4.21
 */
class SingleCycleCPU(implicit val conf: CPUConfig) extends BaseCPU {
  // All of the structures required
  val pc         = dontTouch(RegInit(0.U(64.W)))
  val control    = Module(new Control())
  val registers  = Module(new RegisterFile())
  val aluControl = Module(new ALUControl())
  val alu        = Module(new ALU())
  val immGen     = Module(new ImmediateGenerator())
  val nextpc     = Module(new NextPC())
  val (cycleCount, _) = Counter(true.B, 1 << 30)

  //FETCH
  io.imem.address := pc
  io.imem.valid := true.B

  val instruction = Wire(UInt(32.W))
  when ((pc % 8.U) === 4.U) {
    instruction := io.imem.instruction(63, 32)
  } .otherwise {
    instruction := io.imem.instruction(31, 0)
  }
  val funct3 = instruction(14, 12)

  control.io.opcode := instruction(6, 0)

  registers.io.readreg1 := instruction(19, 15)
  registers.io.readreg2 := instruction(24, 20)
  registers.io.writereg := instruction(11, 7)
  registers.io.writedata := Mux(control.io.toreg, io.dmem.readdata, Mux(control.io.resultselect, immGen.io.sextImm, alu.io.result))
  when (registers.io.writereg =/= 0.U && control.io.regwrite) {
    registers.io.wen := true.B
  } .otherwise {
    registers.io.wen := false.B
  }

  immGen.io.instruction := instruction

  nextpc.io.branch := control.io.branch
  nextpc.io.jumptype := control.io.jumptype
  nextpc.io.inputx := registers.io.readdata1
  nextpc.io.inputy := alu.io.inputy
  nextpc.io.funct3 := funct3
  nextpc.io.pc := pc
  nextpc.io.imm := immGen.io.sextImm

  aluControl.io.aluop := control.io.aluop
  aluControl.io.itype := control.io.itype
  aluControl.io.funct7 := instruction(31, 25)
  aluControl.io.funct3 := instruction(14, 12)
  aluControl.io.wordinst := control.io.wordinst

  alu.io.operation := aluControl.io.operation
  alu.io.inputx := Mux(control.io.src1, pc, registers.io.readdata1)
  alu.io.inputy := MuxCase(0.U, Array((control.io.src2 === 0.U) -> registers.io.readdata2,
                                      (control.io.src2 === 1.U) -> immGen.io.sextImm,
                                      (control.io.src2 === 2.U) -> 4.U))

  io.dmem.address := alu.io.result
  io.dmem.memread := ~control.io.memop(0)
  io.dmem.memwrite := control.io.memop(0)
  io.dmem.valid := control.io.memop(1)
  io.dmem.maskmode := funct3(1, 0)
  io.dmem.sext := ~funct3(2)
  io.dmem.writedata := registers.io.readdata2

  pc := nextpc.io.nextpc
}


/*
 * Object to make it easier to print information about the CPU
 */
object SingleCycleCPUInfo {
  def getModules(): List[String] = {
    List(
      "dmem",
      "imem",
      "control",
      "registers",
      "csr",
      "aluControl",
      "alu",
      "immGen",
      "nextpc"
    )
  }
}

// Main object for testing the CPU setup
import java.nio.file.{Files, Paths}

object SingleCycleCPUNoDebug extends App {
  val outDirStr: String = sys.env.get("HAGENT_BUILD_DIR")
    .filter(_.nonEmpty)
    .map(dir => s"$dir/build_singlecyclecpu_d")
    .getOrElse("./build_singlecyclecpu_d")
  val outDir = Paths.get(outDirStr).toAbsolutePath.normalize
  Files.createDirectories(outDir)

  implicit val conf: CPUConfig = new CPUConfig()
  ChiselStage.emitSystemVerilogFile(
    new SingleCycleCPU,
    args = Array(
      "--target-dir", outDir.toString
    ),
    // Preserve original Chisel constructs; _d build strips // src locators for cleaner output.
    firtoolOpts = Array(
      "-O=debug",                                // minimal optimization -> modules stay close to source
      "--preserve-aggregate=all",                // keep vectors AND bundles as packed arrays / structs
      "--scalarize-public-modules=false",        // keep aggregate ports on the top/public module
      "--scalarize-ext-modules=false",           // keep aggregate ports on blackboxes too
      "--preserve-values=named",                 // keep meaningful signal names
      "--emit-separate-always-blocks",           // one always block per register
      "--lowering-options=disallowMuxInlining",  // Mux/when stay as their own named wires
      "-strip-debug-info",                       // drop // src locators (matches _d output dir)
      "-default-layer-specialization=enable",
      "-disable-all-randomization"
    )
  )
}

object SingleCycleCPUDebug extends App {
  val outDirStr: String = sys.env.get("HAGENT_BUILD_DIR")
    .filter(_.nonEmpty)
    .map(dir => s"$dir/build_singlecyclecpu_nd")
    .getOrElse("./build_singlecyclecpu_nd")
  val outDir = Paths.get(outDirStr).toAbsolutePath.normalize
  Files.createDirectories(outDir)

  implicit val conf: CPUConfig = new CPUConfig()
  ChiselStage.emitSystemVerilogFile(
    new SingleCycleCPU,
    args = Array(
      "--target-dir", outDir.toString
    ),
    // Preserve original Chisel constructs as much as possible (keeps // src locators).
    firtoolOpts = Array(
      "-O=debug",                                // minimal optimization -> modules stay close to source
      "--preserve-aggregate=all",                // keep vectors AND bundles as packed arrays / structs
      "--scalarize-public-modules=false",        // keep aggregate ports on the top/public module
      "--scalarize-ext-modules=false",           // keep aggregate ports on blackboxes too
      "--preserve-values=named",                 // keep meaningful signal names
      "--emit-separate-always-blocks",           // one always block per register
      "--lowering-options=disallowMuxInlining",  // Mux/when stay as their own named wires
      "-default-layer-specialization=enable",
      "-disable-all-randomization"
    )
  )
}
