import logging
from typing import Any

from aura_hw.backends.inference.base import InferenceBackend
from aura_hw.loader import load_inference_class

logger = logging.getLogger(__name__)

class GeneralInferenceBackend(InferenceBackend):
    """
    General Inference backend/wrapper.
    Dynamically loads custom inference runtime from hardware/hw_arch/<hw>/inference/library.py.
    """

    def __init__(self, hardware_type: str) -> None:
        self._hardware_type = hardware_type
        self._delegate = None

    @property
    def hardware_type(self) -> str:
        return self._hardware_type

    def load(self, model_path: str, class_names: list[str] = None) -> None:
        logger.info(f"[GeneralInferenceBackend] Dynamically loading custom inference runtime for '{self._hardware_type}'")
        cls = load_inference_class(self._hardware_type)
        self._delegate = cls()
        
        import inspect
        sig = inspect.signature(self._delegate.load)
        if "class_names" in sig.parameters:
            self._delegate.load(model_path, class_names=class_names)
        else:
            self._delegate.load(model_path)

    def infer(self, inputs: Any) -> Any:
        if self._delegate is None:
            raise RuntimeError("Inference backend is not loaded. Call load() first.")

        if hasattr(self._delegate, "infer"):
            return self._delegate.infer(inputs)
        elif hasattr(self._delegate, "execute_inference"):
            return self._delegate.execute_inference(inputs)
        elif hasattr(self._delegate, "read_value"):
            return self._delegate.read_value(inputs)
        else:
            raise AttributeError(f"Custom inference runtime class has no infer/execute method")

    def unload(self) -> None:
        if self._delegate:
            if hasattr(self._delegate, "unload"):
                self._delegate.unload()
            self._delegate = None

    def device_info(self) -> dict:
        if self._delegate and hasattr(self._delegate, "device_info"):
            return self._delegate.device_info()
            
        return {"hardware_type": self._hardware_type}
