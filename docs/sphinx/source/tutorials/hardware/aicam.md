# Comprehensive Guide: Raspberry Pi AI Camera (Sony IMX500) Integration

This guide provides a structured walkthrough for setting up, optimizing, compiling, packaging, and deploying deep learning models on the Sony IMX500 Intelligent Vision Sensor using a Raspberry Pi 5.

This workflow is based on the official `Sony AITRIOS Raspberry Pi AI Camera Tutorial` [1], the `Raspberry Pi AI Camera Hardware documentation` [2], and `Sony Model Compression Toolkit (MCT)` [3].

---

## Part 1: Compilation & Packaging Phase

This phase processes, quantizes, and compiles full-precision PyTorch models (`.pt`) into hardware-optimized instruction binaries tailored for the Sony IMX500 coprocessor. This step is executed on a host machine (PC or server) with Python 3.10+ and a GPU.

### 1. Environment Initialization

To set up the compilation tools on your host machine, install the Model Compression Toolkit (MCT) and the IMX500 conversion toolchain:

```bash
# Install Model Compression Toolkit
pip install model-compression-toolkit

# Install IMX500 Converter for PyTorch
pip install imx500-converter[pt]

# Install validation and runtime frameworks
pip install torch torchvision onnx
```

### 2. Core Functional Pipeline

Transforming a standard YOLO architecture into a camera-ready executable network package (`.rpk`) involves four stages:

| Stage | Process / Tool | Description | Output Artifact |
|---|---|---|---|
| **1. Model Creation** | PyTorch / TensorFlow | Train a neural network using standard deep learning frameworks. | Full-precision floating-point weights (`your_model.pt`) |
| **2. Optimization** | Model Compression Toolkit (MCT) | Compress and quantize network weights (FP32 to INT8) using calibration images. | Quantized ONNX graph (`model.onnx`) |
| **3. Compilation** | IMX500 Converter | Translate standard format operators to physical instruction blocks for the IMX500. | Compiler bundle archive (`packerOut.zip`) |
| **4. Packaging** | IMX500 Packager | Encapsulate compiled assets and configuration tables into a camera executable. | Deployment ready package (`network.rpk`) |

### 3. Model Preparation & Compilation (on Host Machine)

To perform model quantization and compilation without writing custom converter wrappers, you can execute the export toolchain using the following workflow:

1. **Load weights**: Open your Python interpreter or export script and load your trained PyTorch YOLO model weights.
2. **Define calibration dataset configuration**: Create a dataset YAML config file detailing paths to your calibration images and matching class IDs.
3. **Execute the Ultralytics IMX Export**: Call the native model export method, specifying the format as `"imx"` and pointing to your calibration dataset YAML configuration.
4. **Graph Quantization (MCT)**: The tool will feed the calibration images through the model to determine activation ranges, quantize weight tensors from 32-bit floats (FP32) to 8-bit integers (INT8), and output a quantized ONNX graph.
5. **Instruction compilation**: The pipeline automatically forwards the quantized graph to the `imx500-converter` compiler which maps layers to physical instruction blocks and creates `packerOut.zip`.
6. **Output check**: Verify that the compressed `packerOut.zip` file has been written to your output directory.

---

## Part 2: Model Packaging & Inference (on the Raspberry Pi 5)

This phase runs on the Raspberry Pi 5 with the physical AI Camera attached.

### 1. Dependency Installation

Log in to the Raspberry Pi 5, update system packages, and install the IMX500 runtime firmware, compiler tools, and the Python camera stack:

```bash
# Update repository lists and system packages
sudo apt update && sudo apt full-upgrade -y

# Install the Sony IMX500 runtime firmware
sudo apt install imx500-all -y

# Install packaging tools and Python picamera2
sudo apt install imx500-tools python3-picamera2 python3-opencv -y

# Reboot to load overlays and firmware
sudo reboot
```

### 2. Building the Runtime Package (`.rpk`)

Copy the `packerOut.zip` file generated on your host machine to the Raspberry Pi 5. Run the packaging utility to generate the final camera firmware package (`.rpk`):

```bash
imx500-package -i packerOut.zip -o output_directory
```

This generates `network.rpk` inside `output_directory`.

### 3. Programmatic Inference Steps

To run inference on the Sony IMX500 AI Camera chip programmatically, configure your Python script using the following sequence:

1. **Import camera modules**: Import the `Picamera2` camera stack and the `IMX500` hardware device helper from `picamera2.devices`.
2. **Instantiate the NPU model**: Load the compiled `.rpk` model into memory by instantiating the `IMX500` class with the path to your package file.
3. **Retrieve hardware parameters**: Get the model input dimensions (width and height) and the target camera index from the IMX500 hardware object.
4. **Initialize Picamera2**: Open the camera stream using the specific camera index provided by the IMX500 device instance.
5. **Configure preview resolution**: Configure the main capturing stream to match the desired format (such as RGB888 format) and start the camera preview thread.
6. **Retrieve on-chip detections**: Inside your frame capture loop, request frames from the Picamera2 stream, extract their metadata, and pass them to the `imx.get_outputs(metadata)` method.
7. **Read inferences**: Access the returned detections list, which contains the bounding boxes (`[ymin, xmin, ymax, xmax]`), classes, confidence scores, and detection counts computed entirely by the IMX500 intelligent sensor.
8. **Release request buffers**: Release the request frame resources in each loop cycle to avoid memory exhaustion, and stop the camera stream when terminating the script.

---

## References

* [1] Sony AITRIOS Raspberry Pi AI Camera Guide: <https://developer.aitrios.sony-semicon.com/en/docs/raspberry-pi-ai-camera/raspberry-pi-ai-camera-tutorial?version=2025-09-30&progLang=>
* [2] Raspberry Pi AI Camera Hardware documentation: <https://www.raspberrypi.com/documentation/accessories/ai-camera.html>
* [3] Sony Model Compression Toolkit repository: <https://github.com/SonySemiconductorSolutions/mct-model-optimization>
* [4] Sony IMX500 Converter Utility: <https://developer.aitrios.sony-semicon.com/en/docs/raspberry-pi-ai-camera/imx500-converter?version=3.18.2&progLang=>
* [5] Sony IMX500 Packager Utility: <https://developer.aitrios.sony-semicon.com/en/docs/raspberry-pi-ai-camera/imx500-packager?version=2025-09-30&progLang=>

[1]: https://developer.aitrios.sony-semicon.com/en/docs/raspberry-pi-ai-camera/raspberry-pi-ai-camera-tutorial?version=2025-09-30&progLang=
[2]: https://www.raspberrypi.com/documentation/accessories/ai-camera.html
[3]: https://github.com/SonySemiconductorSolutions/mct-model-optimization
[4]: https://developer.aitrios.sony-semicon.com/en/docs/raspberry-pi-ai-camera/imx500-converter?version=3.18.2&progLang=
[5]: https://developer.aitrios.sony-semicon.com/en/docs/raspberry-pi-ai-camera/imx500-packager?version=2025-09-30&progLang=
