#!/usr/bin/env bash
# Build and install spike (riscv-isa-sim), the golden reference for the cosim
# experiment. It is not packaged by apt or Homebrew's core tap, so it is built
# from source. Linux and macOS; on Windows run this inside WSL.
#
#   cosim/install_spike.sh                 # installs to ~/.local
#   PREFIX=/usr/local cosim/install_spike.sh
#
# Requires sudo for the build dependencies (and for PREFIX outside $HOME).
set -euo pipefail

PREFIX="${PREFIX:-$HOME/.local}"
SPIKE_REF="${SPIKE_REF:-master}"
SRC="${SRC:-${TMPDIR:-/tmp}/riscv-isa-sim}"

# Already root (e.g. `wsl -u root`)? Then sudo is unnecessary and may be absent.
SUDO="sudo"
[[ "$(id -u)" -eq 0 ]] && SUDO=""

if command -v spike >/dev/null 2>&1; then
    echo "==> spike already installed: $(command -v spike)"
    exit 0
fi

echo "==> Installing build dependencies"
case "$(uname -s)" in
    Darwin)
        command -v brew >/dev/null 2>&1 || { echo "error: Homebrew required" >&2; exit 1; }
        brew install dtc automake autoconf
        ;;
    Linux)
        if command -v apt-get >/dev/null 2>&1; then
            $SUDO apt-get update
            $SUDO apt-get install -y git build-essential autoconf automake \
                                    device-tree-compiler
        else
            echo "error: no apt-get; install autoconf, automake, g++ and dtc first" >&2
            exit 1
        fi
        ;;
    *)
        echo "error: unsupported platform $(uname -s); run this inside WSL on Windows" >&2
        exit 1
        ;;
esac

echo "==> Fetching riscv-isa-sim into $SRC"
if [[ -d "$SRC/.git" ]]; then
    git -C "$SRC" fetch --depth 1 origin "$SPIKE_REF"
    git -C "$SRC" checkout -q FETCH_HEAD
else
    rm -rf "$SRC"
    git clone --depth 1 --branch "$SPIKE_REF" \
        https://github.com/riscv-software-src/riscv-isa-sim "$SRC"
fi

echo "==> Building (this takes a few minutes)"
mkdir -p "$SRC/build"
cd "$SRC/build"
../configure --prefix="$PREFIX"
make -j"$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
$SUDO make install

echo
echo "==> Installed to $PREFIX/bin/spike"
case ":$PATH:" in
    *":$PREFIX/bin:"*) ;;
    *)
        echo "    $PREFIX/bin is not on PATH. Add it, e.g.:"
        echo "        echo 'export PATH=\"$PREFIX/bin:\$PATH\"' >> ~/.bashrc"
        ;;
esac
echo "    Then restart the farm backend so it picks the tool up."
