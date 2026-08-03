/*
 * Install commands for the system tools experiments declare in farm.yaml.
 * Keep in sync with the install table in farm/README.md.
 */

/* Rough platform sniff — enough to choose a package manager. */
export function detectOs() {
  const ua = navigator.userAgent || ''
  if (/Windows/i.test(ua)) return 'windows'
  if (/Mac OS X|Macintosh/i.test(ua)) return 'mac'
  return 'linux'
}

const HINTS = {
  clang: {
    mac: 'xcode-select --install',
    linux: 'sudo apt install -y clang',
    windows: 'winget install LLVM.LLVM',
    note: 'any C compiler works; the helper honours CC',
  },
  ngspice: {
    mac: 'brew install ngspice',
    linux: 'sudo apt install -y ngspice',
    windows: 'choco install ngspice',
  },
  verilator: {
    mac: 'brew install verilator',
    linux: 'sudo apt install -y verilator',
    windows: 'wsl -- sudo apt install -y verilator',
    note: 'no native Windows build; runs inside WSL',
  },
  spike: {
    mac: 'bash cosim/install_spike.sh',
    linux: 'bash cosim/install_spike.sh',
    windows: 'wsl -- bash cosim/install_spike.sh',
    note: 'not packaged; the script builds it from source',
  },
  'riscv64-elf-gcc': {
    mac: 'brew install riscv64-elf-gcc riscv64-elf-binutils',
    linux: 'sudo apt install -y gcc-riscv64-unknown-elf',
    windows: 'wsl -- sudo apt install -y gcc-riscv64-unknown-elf',
  },
  'riscv64-unknown-elf-gcc': {
    mac: 'brew install riscv64-elf-gcc riscv64-elf-binutils',
    linux: 'sudo apt install -y gcc-riscv64-unknown-elf',
    windows: 'wsl -- sudo apt install -y gcc-riscv64-unknown-elf',
  },
  sbt: {
    mac: 'brew install sbt',
    linux: 'see scala-sbt.org/download',
    windows: 'winget install sbt.sbt',
  },
}

/* [{ tool, command, note }] for the tools this experiment is missing. */
export function installHints(missing, os = detectOs()) {
  return (missing ?? []).map((tool) => {
    const h = HINTS[tool]
    return {
      tool,
      command: h?.[os] ?? null,
      note: h?.note ?? null,
    }
  })
}
