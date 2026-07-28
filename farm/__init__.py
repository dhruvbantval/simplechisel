"""AutoExperiment Farm core — domain-agnostic experiment records + adapter contract.

The farm runs many kinds of experiment (CPU cosim, ECG, SPICE, compiler diffing)
through one pipeline. Everything here is domain-agnostic on purpose; each science
plugs in as an Adapter that emits ExperimentRecords. See README.md.
"""
from .record import ExperimentRecord, Metric, STATUSES, content_run_id, validate
from .adapter import Adapter

__all__ = [
    "ExperimentRecord",
    "Metric",
    "STATUSES",
    "content_run_id",
    "validate",
    "Adapter",
]
