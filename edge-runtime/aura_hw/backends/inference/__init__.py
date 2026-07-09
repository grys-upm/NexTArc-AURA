"""
Inference backends for AURA HAL.

Each backend targets a specific hardware accelerator architecture.
Import the concrete class you need, or let :mod:`aura_hw.runtime`
select the right one automatically via hardware detection.
"""
from aura_hw.backends.inference.base import InferenceBackend

__all__ = ["InferenceBackend"]
