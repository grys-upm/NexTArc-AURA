# Standalone Guide: Raspberry Pi 5 CPU Inference (ONNX) with Pi Camera Module 3

This guide provides a structured walkthrough for setting up, compiling, and executing deep learning models directly on the Raspberry Pi 5 CPU using the ONNX Runtime engine and capturing frames from the Raspberry Pi Camera Module 3.

This workflow is based on the official `Ultralytics YOLO Export` [1] guide, the `ONNX Runtime documentation` [2], and `Raspberry Pi Camera documentation` [3].

---

## Part 1: Compilation Phase

In this phase, a deep learning model (e.g., YOLO) is trained or loaded in PyTorch (`.pt`) and converted to the optimized Open Neural Network Exchange (`.onnx`) format on a PC or host machine.

### 1. Environment Initialization

To convert the model, your host machine requires Python 3.10+ [4] and the `ultralytics` package. Install them using pip:

```bash
pip install --upgrade pip
pip install ultralytics onnx
```

### 2. Model Export Steps

To convert your model weights to the CPU-optimized ONNX format:

1. **Load model weights**: Load your trained PyTorch weights file (`your_model.pt`) using Python.
2. **Select ONNX format**: Trigger the model's export utility, specifying the output format as `"onnx"`.
3. **Set input resolution**: Enforce the target resolution (such as `imgsz=640`) to lock the neural network input shape.
4. **Lock batch dimension**: Set `batch=1` to optimize execution for single-frame streaming scenarios.
5. **Include Non-Maximum Suppression (NMS)**: Enable NMS embedding inside the exported model graph (`nms=True`). This allows the ONNX Runtime engine to perform box clustering natively, simplifying post-processing.
6. **Set operators version**: Configure the output to target operators version `12` (`opset=12`) for maximum portability across Linux-ARM64 platforms.
7. **File check**: Verify that the generated `.onnx` model has been successfully generated in your directory before copying it to your Raspberry Pi.

---

## Part 2: Inference Phase

This phase is executed directly on the Raspberry Pi 5 CPU running Raspberry Pi OS.

Before starting, ensure the physical camera module is connected and configured on the system. For detailed steps, see the [Pi Camera Module 3 Installation Guide](picamera.md).

### 1. Dependency Installation

On your Raspberry Pi 5, update the system repository packages and install the native camera stack and the `onnxruntime` inference engine:

```bash
# Update package database
sudo apt update && sudo apt upgrade -y

# Install the native Picamera2 library
sudo apt install python3-picamera2 python3-opencv -y

# Install ONNX Runtime and NumPy via pip
pip install onnxruntime>=1.16.0 numpy
```

> [!NOTE]
> Pre-built wheels for `onnxruntime` are fully optimized out of the box for Linux aarch64 (ARM64) running on the Raspberry Pi 5 CPU.

### 2. Programmatic Inference Steps

To execute the real-time inference loop using the Raspberry Pi Camera Module 3 and your compiled ONNX model on the host CPU, structure your execution program according to the following steps:

1. **Import modules**: Load python libraries (`time`, `numpy`, `cv2`, `picamera2`, `onnxruntime`).
2. **Initialize inference session**: Load the `.onnx` model file by instantiating the ONNX Runtime `InferenceSession` class, and query the session to find the input tensor layer name.
3. **Initialize the camera**: Create a new `Picamera2` camera connection context.
4. **Configure preview capture**: Create a camera stream configuration (RGB888 format) matching the desired frame resolution (such as 640x480) and start the camera capturing engine.
5. **Frame Preprocessing**: Within your execution loop, retrieve a frame array from the camera buffer and apply the following steps:
   - Resize the image array to match the input resolution required by your ONNX model (640x640).
   - Divide pixel values by `255.0` to normalize the data array to a `[0.0, 1.0]` range.
   - Transpose the array format from Height-Width-Channel (HWC) to Channel-Height-Width (CHW) order.
   - Insert an additional dimension at the beginning to represent the batch structure (BCHW).
6. **Execute CPU inference**: Pass the normalized BCHW tensor to the ONNX Runtime session `run` method, executing the network layers on the Raspberry Pi 5 CPU.
7. **Read inferences**: Retrieve the output tensors, calculate execution latency, and perform post-processing on class detections or box predictions.
8. **Release camera resources**: Stop the camera capture stream and close the `Picamera2` context upon terminating the script.

---

## References

* [1] Ultralytics YOLO Export Options: <https://docs.ultralytics.com/modes/export/#arguments>
* [2] ONNX Runtime Engine Documentation: <https://onnxruntime.ai/docs/>
* [3] Raspberry Pi Camera Software: <https://www.raspberrypi.com/documentation/computers/camera_software.html>
* [4] Python Downloads: <https://www.python.org/downloads/>

[1]: https://docs.ultralytics.com/modes/export/#arguments
[2]: https://onnxruntime.ai/docs/
[3]: https://www.raspberrypi.com/documentation/computers/camera_software.html
[4]: https://www.python.org/downloads/
