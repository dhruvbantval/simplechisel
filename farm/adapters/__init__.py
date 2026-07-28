"""Farm adapters — one per experiment type (one science each).

They share nothing but the record format: each runs its own tools against its own
golden reference. cosim and compiler-diff came first; control, ecg and physics are
the three domain experiments.
"""
from .cosim import CosimAdapter
from .compiler_diff import CompilerDiffAdapter
from .control import ControlAdapter
from .ecg import EcgAdapter
from .physics import PhysicsAdapter

# Registry so the config file can name an adapter by its type string.
ADAPTERS = {
    a.type: a for a in (
        CosimAdapter(), CompilerDiffAdapter(), ControlAdapter(),
        EcgAdapter(), PhysicsAdapter(),
    )
}

__all__ = [
    "CosimAdapter", "CompilerDiffAdapter", "ControlAdapter",
    "EcgAdapter", "PhysicsAdapter", "ADAPTERS",
]
