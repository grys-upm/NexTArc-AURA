"""
Sony IMX500 sensor/accelerator management module.

This module contains the `IMX500Manager` class, responsible for managing RPK
(Raspberry Pi Package) models compiled for the Raspberry Pi native AI camera (Sony IMX500),
as well as packaging ZIP files to RPK using the host tool `imx500-package`.
"""

import os
from daemon.shared import logger, HARDWARE_TYPE
from daemon.camera import CameraManager, camera_manager


class IMX500Manager:
    """
    Class to manage dynamic loading and inference of Sony IMX500 models on the host.

    Communicates with `CameraManager` to temporarily stop the camera, load the neural
    network RPK model firmware into the camera sensor chip, and restart the camera in AI mode.

    :ivar camera_mgr: Shared camera manager instance in the daemon.
    :type camera_mgr: CameraManager
    :ivar model_path: Path to the temporary file of the RPK model.
    :type model_path: str or None
    :ivar model_hash: SHA-256 hash of the currently loaded model content to avoid reloads.
    :type model_hash: str or None
    """

    def __init__(self, camera_mgr: CameraManager) -> None:
        """
        Initializes a new instance of IMX500Manager.

        :param camera_mgr: Active camera manager to coordinate model loading.
        :type camera_mgr: CameraManager
        """
        self.camera_mgr = camera_mgr
        self.model_path = None
        self.model_hash = None

    def load(self, rpk_bytes: bytes) -> dict:
        """
        Loads the provided RPK model into the Sony IMX500 physical camera sensor.

        If a ZIP file is received instead of a direct RPK (detected by the PK header of ZIPs),
        the method runs the host's native tool `imx500-package` to compile/package
        the ZIP into an `.rpk` file before saving it to a temp file and loading it.

        :param rpk_bytes: Bytes of the model file (.rpk format or .zip file containing the network).
        :type rpk_bytes: bytes
        :return: Dictionary with the status of the operation and the input size if successful.
        :rtype: dict
        :raises RuntimeError: If packaging the ZIP file to RPK on the host fails.
        """
        # Validate that the configured hardware is indeed the Raspberry Pi AI camera (rpi_ai_cam)
        if HARDWARE_TYPE != "rpi_ai_cam":
            return {"status": "error", "error": f"RPi AI Cam is not enabled (configured hardware type: {HARDWARE_TYPE})"}
        
        # Calculate the SHA-256 hash of the input bytes to uniquely identify this model
        import hashlib
        m_hash = hashlib.sha256(rpk_bytes).hexdigest()
        
        # If the model is already loaded on disk and its hash matches, skip loading
        if self.model_path and os.path.exists(self.model_path) and self.model_hash == m_hash:
            logger.info("Sony IMX500 model is already loaded. Skipping reload.")
            return {"status": "success", "input_shape": [640, 640, 3]}

        try:
            # Unload any existing model in the system
            self.unload()
            self.model_hash = m_hash
            
            # Try to import the IMX500 module from the picamera2 package
            HAS_IMX500 = False
            try:
                from picamera2.devices import IMX500
                HAS_IMX500 = True
            except ImportError:
                logger.warning("picamera2.devices.IMX500 not available on host. Using simulated IMX500.")
                
            import tempfile
            import subprocess
            
            # Check if the received buffer corresponds to a ZIP archive (starts with 'PK\x03\x04' header)
            if rpk_bytes.startswith(b"PK\x03\x04"):
                logger.info("Received ZIP archive. Packaging model to RPK using imx500-package on host...")
                # Create a temporary directory to perform the packaging
                with tempfile.TemporaryDirectory() as packaging_dir:
                    zip_path = os.path.join(packaging_dir, "packerOut.zip")
                    # Write the temporary compressed file to disk
                    with open(zip_path, "wb") as f:
                        f.write(rpk_bytes)
                    
                    try:
                        # Prepare the call to the host packager 'imx500-package'
                        cmd = ["imx500-package", "-i", zip_path, "-o", packaging_dir]
                        logger.info(f"Running command on host: {' '.join(cmd)}")
                        # Run the command capturing stdout and stderr to facilitate debugging
                        res = subprocess.run(cmd, check=True, capture_output=True, text=True)
                        
                        # The command generates a network.rpk file in the output directory
                        generated_rpk = os.path.join(packaging_dir, "network.rpk")
                        if os.path.exists(generated_rpk):
                            # Read the packaged RPK file and replace the rpk_bytes variable in memory
                            with open(generated_rpk, "rb") as f:
                                rpk_bytes = f.read()
                            logger.info("Successfully packaged model to RPK on host.")
                        else:
                            raise FileNotFoundError("network.rpk was not generated by imx500-package")
                    except Exception as e:
                        stderr_out = getattr(e, 'stderr', '')
                        logger.error(f"Failed to package model using imx500-package on host: {e}. Stderr: {stderr_out}")
                        raise RuntimeError(f"Failed to package ZIP model to RPK on host: {e} (details: {stderr_out})")

            # Create the final temporary file to dump the RPK bytes ready for the chip
            fd, path = tempfile.mkstemp(suffix=".rpk")
            with os.fdopen(fd, "wb") as tmp:
                tmp.write(rpk_bytes)
            self.model_path = path
            
            logger.info(f"Loading IMX500 RPK model from {path}...")
            
            # Temporarily stop the secondary camera capture thread before changing the device firmware
            self.camera_mgr.stop()
            
            # If physical IMX500 hardware is available, instantiate it
            if HAS_IMX500:
                self.camera_mgr.imx500 = IMX500(self.model_path)
                h, w = self.camera_mgr.imx500.get_input_size()
            else:
                # Simulated IMX500 device instance
                class SimulatedIMX500:
                    def __init__(self):
                        self.camera_num = 0
                    def get_input_size(self):
                        return (640, 640)
                    def show_network_fw_progress_bar(self):
                        pass
                self.camera_mgr.imx500 = SimulatedIMX500()
                h, w = 640, 640
                
            # Restart the camera capture thread to apply the new IMX500 device and start AI preview
            self.camera_mgr.start()
            
            logger.info(f"IMX500 model loaded successfully. Input shape: {w}x{h}")
            return {"status": "success", "input_shape": [h, w, 3]}
        except Exception as e:
            logger.error(f"Error loading IMX500 model: {e}")
            # If loading fails, revert everything back to no model state
            self.unload()
            return {"status": "error", "error": str(e)}

    def infer(self) -> dict:
        """
        Gets the most recent detections calculated by the Sony IMX500 sensor asynchronously.

        Since the IMX500 runs inside the camera firmware itself, detections are captured
        along with the frame in the `CameraManager` secondary thread. This method simply
        retrieves that result safely.

        :return: Dictionary with the list of detections found ("detections") or an error message.
        :rtype: dict
        """
        # If no IMX500 device is initialized or active
        if self.camera_mgr.imx500 is None:
            return {"status": "error", "error": "No model loaded"}
        
        # Read the last detection output using mutex lock to avoid race conditions with the camera thread
        with self.camera_mgr.lock:
            outputs = self.camera_mgr.latest_outputs
            
        # If no outputs are available yet
        if outputs is None:
            return {"status": "success", "detections": []}
            
        return {"status": "success", "detections": outputs}

    def unload(self) -> None:
        """
        Unloads the IMX500 model, stopping the camera, cleaning up the sensor firmware instance,
        and restarting the camera in standard mode without a neural network.
        """
        # If the camera has an IMX500 AI device loaded
        if self.camera_mgr.imx500 is not None:
            # Temporarily stop the camera
            self.camera_mgr.stop()
            # Remove the IMX500 object to revert to standard camera
            self.camera_mgr.imx500 = None
            # Restart the camera without firmware acceleration
            self.camera_mgr.start()
            
        # Remove the temporary .rpk file from disk if it exists
        if self.model_path and os.path.exists(self.model_path):
            try:
                os.remove(self.model_path)
            except Exception:
                pass
            self.model_path = None
        # Clear the model hash
        self.model_hash = None


# Unique instance (singleton) of the IMX500 manager
imx500_manager = IMX500Manager(camera_manager)
