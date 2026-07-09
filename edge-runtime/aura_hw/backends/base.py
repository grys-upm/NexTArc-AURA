"""
Compatibility re-export — InferenceBackend base class.

New code should import directly from:

    from aura_hw.backends.inference.base import InferenceBackend
"""
from aura_hw.backends.inference.base import InferenceBackend  # noqa: F401

__all__ = ["InferenceBackend"]
