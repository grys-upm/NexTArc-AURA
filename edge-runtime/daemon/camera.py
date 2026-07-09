"""
Physical and simulated camera management module.

This module contains the `CameraManager` class, responsible for interacting with the
physical Raspberry Pi camera module (via `Picamera2`) or simulating its behavior
using images generated in memory (using `Pillow`) if not available.
"""

import time
import threading
import numpy as np
from daemon.shared import logger, HARDWARE_TYPE, CAMERA_ENABLED, HAS_PILLOW

# Try to import Pillow (PIL) for simulation if the library is available
if HAS_PILLOW:
    from PIL import Image, ImageDraw


class CameraManager:
    """
    Class to manage the camera lifecycle and capture frames to memory.

    This class controls the initialization, background execution via a thread,
    image capture (physical or simulated), frame synchronization, and stopping
    the camera (Picamera2).

    :ivar picam2: Native Picamera2 object instance (if enabled and available).
    :type picam2: Picamera2 or None
    :ivar imx500: IMX500 manager instance if running on a Raspberry Pi AI Camera.
    :type imx500: IMX500Manager or None
    :ivar is_active: Current state of the camera (active/inactive).
    :type is_active: bool
    :ivar latest_frame: Bytes of the last captured frame (RGB888 format).
    :type latest_frame: bytes or None
    :ivar latest_outputs: Last raw tensor outputs/inferences obtained from the hardware (e.g. IMX500).
    :type latest_outputs: list or None
    :ivar lock: Mutex lock to protect concurrent access to captures.
    :type lock: threading.Lock
    :ivar thread: Background thread for the capture loop.
    :type thread: threading.Thread or None
    :ivar stop_event: Event to signal the capture thread to stop.
    :type stop_event: threading.Event
    """

    def __init__(self) -> None:
        """
        Initializes a new instance of CameraManager with default values.
        """
        self.picam2 = None
        self.imx500 = None
        self.is_active = False
        self.latest_frame = None
        self.latest_outputs = None
        self.lock = threading.Lock()
        self.thread = None
        self.stop_event = threading.Event()

    def start(self) -> None:
        """
        Starts the camera and launches the background capture thread.

        If the physical camera is enabled (`CAMERA_ENABLED`), initializes `Picamera2`
        and configures the resolution and format (RGB888). Otherwise, enables the
        fallback simulation mode.
        
        :raises Exception: If an error occurs during the physical initialization of the device.
        """
        # Stop any previous execution to ensure a clean state
        self.stop()
        
        # Clear the stop event to allow the loop to run
        self.stop_event.clear()
        
        # Reset the last frame data and results
        self.latest_frame = None
        self.latest_outputs = None
        
        # Check if the camera is enabled in the configuration
        if CAMERA_ENABLED:
            logger.info("Initializing native Picamera2 (Camera Module 3)...")
            try:
                # Lazy import to avoid failures if Picamera2 is not installed on the system
                from picamera2 import Picamera2
                
                # If there is an associated IMX500 manager, initialize the native Sony AI camera
                if self.imx500 is not None:
                    # Initialize Picamera2 with the camera number corresponding to the IMX500
                    self.picam2 = Picamera2(self.imx500.camera_num)
                    
                    # Create preview configuration for the AI camera (640x480 RGB888, 12 buffers)
                    config = self.picam2.create_preview_configuration(
                        main={"size": (640, 480), "format": "RGB888"},
                        buffer_count=12
                    )
                    
                    # Show progress bar if supported by the AI camera (network firmware loading)
                    if hasattr(self.imx500, "show_network_fw_progress_bar"):
                        self.imx500.show_network_fw_progress_bar()
                else:
                    # Initialize Picamera2 in a standard way without IMX500 module
                    self.picam2 = Picamera2()
                    
                    # Create standard preview configuration (640x480 RGB888)
                    config = self.picam2.create_preview_configuration(
                        main={"size": (640, 480), "format": "RGB888"}
                    )
                
                # Apply configuration to the camera
                self.picam2.configure(config)
                
                # Start the camera without showing the preview in a native window
                self.picam2.start(show_preview=False)
                self.is_active = True
                logger.info("Picamera2 started successfully.")
            except Exception as e:
                logger.error(f"Error starting Picamera2: {e}")
                self.picam2 = None
                self.is_active = False
        else:
            # Simulated fallback when camera is disabled in components_config.yaml
            logger.info("Picamera2 is disabled via configuration. Simulated fallback will be used.")
            self.is_active = True

        # Create and launch the secondary thread (daemon=True) to capture asynchronously
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _capture_loop(self) -> None:
        """
        Background capture loop.

        If the physical Picamera2 camera is started, performs native captures
        (with or without IMX500 chip metadata). If not available, simulates
        moving images (using Pillow) or generates a fallback black buffer.
        """
        logger.info("Camera capture loop started.")
        # Runs continuously until stopped with the stop_event
        while not self.stop_event.is_set():
            if self.picam2:
                try:
                    # If the IMX500 accelerator is active on the physical camera
                    if self.imx500:
                        # Request a native capture from Picamera2
                        request = self.picam2.capture_request()
                        
                        # Extract metadata associated with this frame
                        metadata = request.get_metadata()
                        
                        # Convert the captured frame ("main" channel) into a numpy array
                        frame = request.make_array("main")
                        
                        # Extract raw outputs/tensors using the IMX500 manager and metadata
                        outputs = self.imx500.get_outputs(metadata)
                        
                        # Convert the numpy array to raw flat bytes (RGB)
                        frame_bytes = frame.tobytes()
                        
                        # Acquire the lock to update variables safely
                        with self.lock:
                            self.latest_frame = frame_bytes
                            self.latest_outputs = outputs
                        
                        # Release the physical capture request
                        request.release()
                    else:
                        # Standard native capture (without IMX500 AI coprocessor)
                        frame = self.picam2.capture_array()
                        
                        # Convert the image numpy array to raw flat bytes (RGB)
                        frame_bytes = frame.tobytes()
                        
                        # Update the latest captured frame safely
                        with self.lock:
                            self.latest_frame = frame_bytes
                            self.latest_outputs = None
                except Exception as e:
                    logger.error(f"Error in physical camera capture loop: {e}")
                    # Wait a brief moment before retrying to avoid high-speed infinite loops
                    time.sleep(0.1)
            else:
                # Simulation/fallback flow when no physical camera hardware is available
                outputs = None
                
                # If configured hardware type is Raspberry Pi AI Cam but we are simulating
                if HARDWARE_TYPE == "rpi_ai_cam" and self.imx500 is not None:
                    # Generate simulated detections: bounding box at coordinates (100, 100, 300, 300)
                    boxes = np.array([[100.0, 100.0, 300.0, 300.0]], dtype=np.float32)
                    # Mapped class 1: divide by 256.0 to simulate the native API encoding
                    classes = np.array([1.0 / 256.0], dtype=np.float32)
                    # Simulated confidence score of 85%
                    scores = np.array([0.85], dtype=np.float32)
                    # Number of detections: 1
                    count = np.array([1], dtype=np.float32)
                    outputs = [boxes, classes, scores, count]

                # If Pillow is available, generate a dynamic image with moving rectangles
                if HAS_PILLOW:
                    try:
                        # Create a new image in RGB format with a dark background color
                        img = Image.new("RGB", (640, 480), color=(30, 32, 36))
                        draw = ImageDraw.Draw(img)
                        
                        # Calculate an oscillating temporal position for a horizontal red bar
                        t = int(time.time() * 20) % 480
                        draw.rectangle([0, t, 640, min(t+30, 480)], fill=(235, 69, 75))
                        
                        # Calculate an oscillating temporal position for a vertical blue bar
                        t2 = int(time.time() * 30) % 640
                        draw.rectangle([t2, 0, min(t2+30, 640), 480], fill=(114, 137, 218))
                        
                        # Convert the simulated image to raw flat bytes (RGB)
                        frame_bytes = img.tobytes()
                        
                        # Save the frame and simulated results safely
                        with self.lock:
                            self.latest_frame = frame_bytes
                            self.latest_outputs = outputs
                    except Exception as e:
                        logger.error(f"Error in simulated capture loop: {e}")
                else:
                    # If no Pillow, generate an empty frame (640x480 RGB888 black image)
                    with self.lock:
                        self.latest_frame = bytes(640 * 480 * 3)
                        self.latest_outputs = outputs
                
                # Wait 100 milliseconds to simulate an approximate refresh rate of 10 FPS
                time.sleep(0.1)

    def capture_raw(self) -> bytes:
        """
        Returns the flat bytes of the last captured frame (RGB888).

        If no frame is available yet, returns an empty buffer of size 640x480x3.

        :return: Raw byte array of the frame (RGB888 format).
        :rtype: bytes
        """
        with self.lock:
            frame = self.latest_frame
        
        # If a frame has already been captured, return it directly
        if frame is not None:
            return frame
            
        # Otherwise, return a flat buffer filled with zeros (black)
        return bytes(640 * 480 * 3)

    def stop(self) -> None:
        """
        Stops the camera capture and closes associated Picamera2 resources.
        """
        # Signal the capture thread to terminate its loop
        self.stop_event.set()
        
        # If the physical camera was initialized, try to stop it
        if self.picam2:
            try:
                self.picam2.stop()
                logger.info("Picamera2 stopped successfully.")
            except Exception as e:
                logger.error(f"Error stopping Picamera2: {e}")
        
        # If the capture thread exists, wait for it to finish execution (max 2 seconds)
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None
            
        # Try to close the physical camera port to release hardware
        if self.picam2:
            try:
                self.picam2.close()
                logger.info("Picamera2 closed successfully.")
            except Exception as e:
                logger.error(f"Error closing Picamera2: {e}")
            self.picam2 = None
            
        # Mark the camera manager state as inactive
        self.is_active = False


# Unique instance (singleton) to be shared in the daemon
camera_manager = CameraManager()
