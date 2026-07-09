"""
Abstract base class for all AURA inference backends.

Each hardware accelerator target (Hailo, ONNX, IMX500, TensorRT)
implements this interface so the rest of the runtime is fully
hardware-agnostic.

Subclasses may also override :meth:`device_info` to report
accelerator-specific metadata (firmware, SDK version, etc.) that is
surfaced in telemetry and ``local_state.json``.
"""
from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class InferenceBackend(ABC):
    """Hardware-specific inference backend interface.

    Concrete subclasses must implement :meth:`load`, :meth:`infer`,
    :meth:`unload`, and the :attr:`hardware_type` property.
    """

    @abstractmethod
    def load(self, model_path: str) -> None:
        """Load a compiled model file into the accelerator.

        Args:
            model_path: Absolute path to the compiled model.
                        Expected format depends on the backend
                        (``.hef`` for Hailo, ``.onnx`` for RPi CPU,
                        ``packerOut.zip`` for IMX500).

        Raises:
            RuntimeError: If the required SDK is not installed.
            FileNotFoundError: If ``model_path`` does not exist.
        """
        ...

    @abstractmethod
    def infer(self, inputs: "np.ndarray | dict | None") -> Any:
        """Execute a single inference pass.

        Args:
            inputs: Input tensor(s). Pass ``None`` for sensor-driven
                    backends (e.g. IMX500) where the hardware captures
                    input internally, or when the frame is already
                    pre-loaded into the accelerator pipeline.

        Returns:
            Raw model outputs. Structure varies by backend.
        """
        ...

    @abstractmethod
    def unload(self) -> None:
        """Release the model and free all accelerator resources."""
        ...

    @property
    @abstractmethod
    def hardware_type(self) -> str:
        """Canonical hardware identifier for this backend.

        Returns:
            One of ``"hailo8"``, ``"hailo8l"``, ``"rpi_ai_cam"``,
            ``"rpi"``, ``"jetson_orin_nano"``.
        """
        ...

    def device_info(self) -> dict:
        """Return a dict describing the accelerator connected to this backend.

        Subclasses should override this to report accelerator model,
        firmware version, SDK version, etc.

        Returns:
            A dict with hardware-specific metadata. Common keys:

            * ``hardware_type`` — matches :attr:`hardware_type`.
            * ``accelerator``   — accelerator model string.
            * ``sdk``           — SDK / runtime package name.
            * ``sdk_version``   — version string.
            * ``firmware``      — firmware version, if available.
        """
        return {"hardware_type": self.hardware_type}
