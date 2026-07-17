# Makefile — Verilog generation targets, one per runner.toml profile.
# Each target runs the profile's compile command and emits .sv into build_<profile>/.

# profile -> sbt main class (from runner.toml [<profile>.api.compile])
MAIN_gcd               = gcd.GCD
MAIN_singlecyclecpu_nd = dinocpu.SingleCycleCPUNoDebug
MAIN_singlecyclecpu_d  = dinocpu.SingleCycleCPUDebug
MAIN_pipelined_d       = dinocpu.pipelined.PipelinedDebug
MAIN_pipelined_nd      = dinocpu.pipelined.PipelinedNoDebug
MAIN_dualissue_d       = dinocpu.pipelined.PipelinedDualIssueDebug
MAIN_dualissue_nd      = dinocpu.pipelined.PipelinedDualIssueNoDebug

PROFILES = gcd singlecyclecpu_nd singlecyclecpu_d pipelined_d pipelined_nd dualissue_d dualissue_nd

.PHONY: all $(PROFILES) lint clean help cosim cosim-gen

all: $(PROFILES)

$(PROFILES):
	sbt "runMain $(MAIN_$@)"

# DINO <-> Spike co-simulation over cosim/asm_tests/ (see cosim/README.md)
cosim:
	bash cosim/run_cosim.sh

# Generate RV64I tests via riscv-dv (needs python3.10-3.12; see cosim/generator/)
cosim-gen:
	bash cosim/generator/gen_tests.sh

lint:
	sbt scapegoat

clean:
	rm -rf build_* target

help:
	@echo "Targets:"
	@printf "  %-19s %s\n" \
		all "build every profile (default)" \
		$(foreach p,$(PROFILES),$(p) 'sbt "runMain $(MAIN_$(p))" -> build_$(p)/') \
		lint "sbt scapegoat" \
		clean "rm -rf build_* target"
