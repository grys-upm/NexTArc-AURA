"""
Hailo neural network accelerator management module.

This module contains the `HailoManager` class, responsible for dynamically loading
models in HEF (Hailo Executable Format) format and running inferences using the
host library `picamera2.devices.Hailo`.
"""

import os
from daemon.shared import logger, HARDWARE_TYPE


class HailoManager:
    """
    Class to manage dynamic loading and inference of Hailo models on the host.

    Allows loading a HEF model temporarily, initializing the execution context
    with Hailo-8 or Hailo-8L hardware, and performing inferences on images passed in bytes.

    :ivar hailo: Hailo device object instance from picamera2.devices to interact with the hardware.
    :type hailo: Hailo or None
    :ivar model_path: Path to the temporary file where the HEF model loaded in memory was saved.
    :type model_path: str or None
    """

    def __init__(self) -> None:
        """
        Initializes a new instance of HailoManager with empty values.
        """
        self.hailo = None
        self.model_path = None

    def load(self, hef_bytes: bytes) -> dict:
        """
        Dynamically loads the HEF model supplied in bytes into the Hailo device.

        Saves the bytes to a temporary .hef file and then instances the Hailo
        device object. Resets static internal variables to avoid known bugs
        in picamera2 when performing successive loads.

        :param hef_bytes: Bytes of the HEF model file.
        :type hef_bytes: bytes
        :return: Dictionary indicating the process status ("success" or "error") along with the expected input shape if successful.
        :rtype: dict
        """
        # Verify that the configured hardware type corresponds to a Hailo device
        if HARDWARE_TYPE not in ("hailo8", "hailo8l"):
            return {"status": "error", "error": f"Hailo is not enabled (configured hardware type: {HARDWARE_TYPE})"}
        try:
            # Unload the current model to ensure a clean state
            self.unload()
            
            # Try to dynamically import the native Hailo module
            try:
                from picamera2.devices import Hailo
            except ImportError:
                return {"status": "error", "error": "Hailo runtime library (picamera2.devices.Hailo) not available on host"}
                
            # Workaround for picamera2 bug where the static TARGET variable is not reset on release
            try:
                Hailo.TARGET = None
                Hailo.TARGET_REF_COUNT = 0
            except Exception as e:
                logger.warning(f"Failed to reset Hailo target variables: {e}")
                
            # Create an exclusive temporary file on disk to dump the HEF model bytes
            import tempfile
            fd, path = tempfile.mkstemp(suffix=".hef")
            
            # Open the temporary file descriptor safely in binary write mode
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(hef_bytes)
            self.model_path = path
            
            logger.info(f"Loading Hailo HEF model from {path}...")
            # Instance the Hailo device class with the temporary file path
            self.hailo = Hailo(self.model_path)
            # Enter the context manager to initialize the connection to the Hailo hardware
            self.hailo.__enter__()
            
            # Get the input shape expected by the model (Height, Width, Channels)
            h, w, c = self.hailo.get_input_shape()
            logger.info(f"Hailo HEF model loaded successfully. Input shape: {w}x{h}")
            return {"status": "success", "input_shape": [h, w, c]}
        except Exception as e:
            logger.error(f"Error loading Hailo model: {e}")
            # In case of error, clean up all created temporary resources
            self.unload()
            return {"status": "error", "error": str(e)}

    def infer(self, img_bytes: bytes, w: int, h: int) -> dict:
        """
        Runs inference on the loaded Hailo model using an image in bytes.

        Performs transformations on the image using Numpy and OpenCV to fit the
        input shape required by the model.

        :param img_bytes: Bytes of the frame in flat RGB format.
        :type img_bytes: bytes
        :param w: Original width of the provided image.
        :type w: int
        :param h: Original height of the provided image.
        :type h: int
        :return: Dictionary with the result of the detections obtained from the inference or an error message.
        :rtype: dict
        """
        # If no model is currently loaded in memory, abort the inference
        if not self.hailo:
            return {"status": "error", "error": "No model loaded"}
        try:
            import numpy as np
            import cv2
            # Reconstruct the NumPy array from the image bytes buffer
            img = np.frombuffer(img_bytes, dtype=np.uint8).reshape((h, w, 3)).copy()
            
            # Get the dimensions that the loaded model expects as input
            model_h, model_w, _ = self.hailo.get_input_shape()
            
            # If the frame does not match the size expected by the model, resize it
            if img.shape[0] != model_h or img.shape[1] != model_w:
                img = cv2.resize(img, (model_w, model_h))
                
            # Run the inference synchronously on the preprocessed image
            detections = self.hailo.run(img)
            return {"status": "success", "detections": detections}
        except Exception as e:
            logger.error(f"Error during Hailo inference: {e}")
            return {"status": "error", "error": str(e)}

    def unload(self) -> None:
        """
        Releases the loaded Hailo model, closing its hardware context and removing the temporary file.
        """
        # If there is a Hailo instance running
        if self.hailo:
            try:
                # Exit the Hailo device context to release the chip and memory
                self.hailo.__exit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error exiting Hailo context: {e}")
            self.hailo = None
            
        # Reset the static global variables of the class in picamera2 again
        try:
            from picamera2.devices import Hailo
            Hailo.TARGET = None
            Hailo.TARGET_REF_COUNT = 0
        except Exception:
            pass
            
        # If the temporary file exists on disk, try to remove it from the system
        if self.model_path and os.path.exists(self.model_path):
            try:
                os.remove(self.model_path)
            except Exception:
                pass
            self.model_path = None


# Unique instance (singleton) of the Hailo manager
hailo_manager = HailoManager()
