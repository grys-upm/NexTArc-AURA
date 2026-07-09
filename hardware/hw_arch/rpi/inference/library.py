"""
AURA RPi CPU Inference Backend.
===============================
Runs neural network inference locally using ONNX Runtime directly on Raspberry Pi 5.
"""
from __future__ import annotations

import logging
import os
from typing import Any

import numpy as np

# Setup logging
logger = logging.getLogger(__name__)


class RPiCPUBackend:
    """
    RPi CPU inference backend using ONNX Runtime.

    Loads an optimized ONNX model and executes multi-threaded inference.
    Designed to be loaded dynamically by GeneralInferenceBackend.
    """

    def __init__(self) -> None:
        """
        Initializes the client backend properties.
        """
        self._session = None
        self._input_name = None
        self._input_shape = None
        self._output_names = []
        self._num_classes = None
        self._class_names = []

    def load(self, model_path: str, class_names: list[str] = None) -> None:
        """
        Loads the ONNX model into memory using ONNX Runtime.

        :param model_path: Disk path to the exported ONNX model.
        :type model_path: str
        :param class_names: Optional class label strings.
        :type class_names: list[str] or None
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model path does not exist: {model_path}")

        import onnxruntime as ort
        
        logger.info(f"Loading ONNX model for RPi CPU: {model_path}")
        # Initialize InferenceSession with CPUExecutionProvider
        self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        
        # Retrieve input metadata
        inputs = self._session.get_inputs()
        self._input_name = inputs[0].name
        self._input_shape = inputs[0].shape  # e.g. [1, 3, 640, 640]
        
        # Retrieve output metadata
        self._output_names = [out.name for out in self._session.get_outputs()]
        
        # Try to parse class count from model metadata
        self._num_classes = None
        if class_names:
            self._class_names = class_names
            self._num_classes = len(class_names)
            logger.info(f"Using {self._num_classes} classes from explicit deploy payload: {self._class_names}")
        else:
            try:
                meta = self._session.get_modelmeta().custom_metadata_map
                if "names" in meta:
                    import ast
                    names_dict = ast.literal_eval(meta["names"])
                    self._class_names = [names_dict[i] for i in sorted(names_dict.keys())]
                    self._num_classes = len(names_dict)
                    logger.info(f"Detected {self._num_classes} classes from ONNX metadata: {self._class_names}")
            except Exception as e:
                logger.warning(f"Could not parse class names from metadata: {e}")

        # Fallback to output shape dimension if nms=False
        if self._num_classes is None:
            try:
                outputs = self._session.get_outputs()
                if len(outputs) == 1:
                    shape = outputs[0].shape
                    if len(shape) == 3 and isinstance(shape[1], int) and shape[1] > 4:
                        self._num_classes = shape[1] - 4
                        logger.info(f"Deduced {self._num_classes} classes from output shape {shape}.")
            except Exception:
                pass

        if self._num_classes is None:
            self._num_classes = 80
            logger.info(f"Defaulting to {self._num_classes} classes.")

    def infer(self, inputs: Any) -> dict[str, np.ndarray]:
        """
        Executes inference using ONNX Runtime.

        :param inputs: Input image ndarray of format HWC or preprocessed NCHW.
        :type inputs: Any
        :return: Reconstructed predictions matching {"output0": boxes_array}.
        :rtype: dict
        """
        if self._session is None:
            raise RuntimeError("Model is not loaded. Call load() first.")

        if inputs is None:
            return {}

        # Handle raw HWC image (numpy.ndarray of shape [H, W, 3]) by applying standard resizing/normalization
        if isinstance(inputs, np.ndarray) and len(inputs.shape) == 3:
            import cv2
            h_target = 640
            w_target = 640
            if isinstance(self._input_shape, (list, tuple)):
                if len(self._input_shape) >= 3 and isinstance(self._input_shape[2], int):
                    h_target = self._input_shape[2]
                if len(self._input_shape) >= 4 and isinstance(self._input_shape[3], int):
                    w_target = self._input_shape[3]
            
            img = cv2.resize(inputs, (w_target, h_target))
            img = img.astype(np.float32) / 255.0
            img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
            inputs = np.expand_dims(img, axis=0)  # CHW -> NCHW

        # Run ONNX Runtime session
        ort_outputs = self._session.run(None, {self._input_name: inputs})

        # Reconstruct outputs to fit format expected by post-inference user scripts if model contains embedded NMS
        is_nms_output = False
        if len(self._output_names) == 1:
            out_val = ort_outputs[0]
            if len(out_val.shape) == 3 and out_val.shape[2] == 6:
                is_nms_output = True

        if len(self._output_names) > 1 or is_nms_output:
            try:
                bboxes = None
                scores = None
                classes = None
                
                if is_nms_output:
                    # Single output contains [x1, y1, x2, y2, confidence, class_id]
                    bboxes = ort_outputs[0][..., :4]
                    scores = ort_outputs[0][..., 4]
                    classes = ort_outputs[0][..., 5]
                else:
                    # Locate bboxes, scores, and classes outputs
                    for i, name in enumerate(self._output_names):
                        out_val = ort_outputs[i]
                        shape = out_val.shape
                        if len(shape) == 3 and shape[2] == 4:
                            bboxes = out_val
                        elif len(shape) == 2:
                            if scores is None:
                                scores = out_val
                            else:
                                classes = out_val
                        elif len(shape) == 3 and shape[2] != 4:
                            scores = out_val
                
                if bboxes is not None and scores is not None:
                    if classes is None:
                        if len(scores.shape) == 3:  # (1, num_detections, num_classes)
                            classes = np.argmax(scores, axis=2)
                            scores = np.max(scores, axis=2)
                        else:
                            classes = np.zeros_like(scores)

                    num_detections = bboxes.shape[1]
                    max_class_id = int(np.max(classes)) if len(classes) > 0 else 0
                    num_classes = max(self._num_classes, max_class_id + 1)
                    
                    # Create mock array matching YOLOv8 raw output format (1, 4 + num_classes, num_detections)
                    mock_out = np.zeros((1, 4 + num_classes, num_detections), dtype=np.float32)
                    
                    for d in range(num_detections):
                        # Convert bounding box [x1, y1, x2, y2] to center coordinates [cx, cy, w, h]
                        x1, y1, x2, y2 = bboxes[0, d]
                        w = x2 - x1
                        h = y2 - y1
                        cx = x1 + w / 2.0
                        cy = y1 + h / 2.0
                        
                        mock_out[0, 0, d] = cx
                        mock_out[0, 1, d] = cy
                        mock_out[0, 2, d] = w
                        mock_out[0, 3, d] = h
                        
                        class_id = int(classes[0, d])
                        score = scores[0, d]
                        if 0 <= class_id < num_classes:
                            mock_out[0, 4 + class_id, d] = score
                            
                    return {"output0": mock_out}
            except Exception as e:
                logger.error(f"Failed to reconstruct NMS outputs: {e}")
                # Fallback to dictionary map
                return {name: ort_outputs[i] for i, name in enumerate(self._output_names)}

        # Standard single output format
        return {self._output_names[0]: ort_outputs[0]}

    def unload(self) -> None:
        """
        De-allocates the ONNX session context to reclaim memory resources.
        """
        self._session = None
        self._input_name = None
        self._input_shape = None
        self._output_names = []
        logger.info("ONNX model unloaded")

    def device_info(self) -> dict[str, Any]:
        """
        Collects active SDK and hardware descriptor details.

        :return: Device metrics dictionary.
        :rtype: dict
        """
        import onnxruntime as ort
        return {
            "hardware_type": "rpi",
            "accelerator": "RPi CPU (ONNX)",
            "sdk": "onnxruntime",
            "sdk_version": getattr(ort, "__version__", "unknown"),
            "class_names": getattr(self, "_class_names", [])
        }
