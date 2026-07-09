# Comprehensive Guide: Hailo-8/8L Object Detection Integration

This guide provides a structured walkthrough for setting up, optimizing, and deploying deep learning models on the Hailo-8 and Hailo-8L Neural Processing Units (NPUs).

This workflow is based on the `LukeDitria/RasPi_YOLO` [1] repository and official `Hailo documentation` [2][3].

---

## Part 1: Compilation Phase

This phase requires a robust host environment (WSL - Ubuntu 24.04 on Windows, 16+ GB RAM, and a dedicated NVIDIA GPU) to process the quantization and physical hardware mapping of the model.

### 1. Environment Initialization

#### CUDA Toolkit (v12.9)
Execute the following inside your WSL Ubuntu terminal to install the necessary GPU acceleration libraries [4]:

```bash
wget https://developer.download.nvidia.com/compute/cuda/repos/wsl-ubuntu/x86_64/cuda-wsl-ubuntu.pin
sudo mv cuda-wsl-ubuntu.pin /etc/apt/preferences.d/cuda-repository-pin-600
wget https://developer.download.nvidia.com/compute/cuda/12.9.1/local_installers/cuda-repo-wsl-ubuntu-12-9-local_12.9.1-1_amd64.deb
sudo dpkg -i cuda-repo-wsl-ubuntu-12-9-local_12.9.1-1_amd64.deb
sudo cp /var/cuda-repo-wsl-ubuntu-12-9-local/cuda-*-keyring.gpg /usr/share/keyrings/
sudo apt-get update
sudo apt-get -y install cuda-toolkit-12-9
```

#### Docker Engine
Docker is required to run the isolated Hailo AI Software Suite [5].

```bash
sudo apt-get update
sudo apt-get install ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo \"${UBUNTU_CODENAME:-$VERSION_CODENAME}\") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Grant your user Docker privileges and verify the installation:

```bash
sudo usermod -aG docker ${USER}
sudo docker run hello-world
```

> [!NOTE]
> Log out and log back into your WSL instance for the user group changes to take effect.

### 2. Core Functional Pipeline

Transforming a standard YOLO architecture into a deployment-ready `.hef` binary involves four major functional stages:

| Stage | Process | Output Artifact |
|---|---|---|
| **1. Model Training** | Train the neural network on custom datasets using GPU acceleration. | Floating-point PyTorch weights (`best.pt`) |
| **2. Graph Export** | Translate the PyTorch graph to an intermediate format and strip hardware-redundant layers. | Open Neural Network Exchange file (`.onnx`) |
| **3. Calibration** | Process exactly 1024 raw images for accurate 8-bit dynamic range quantization. | Processed Image directory (`calib/`) |
| **4. Compilation** | Fuse the model and calibration data to map instructions onto physical compute nodes. | Hailo Executable Format (`.hef`) |

### 3. Model & Asset Preparation

Before engaging the compiler, the model graph and the calibration dataset must be heavily optimized on the host machine.

#### Graph Export Requirements
The PyTorch model must be structurally verified and exported into the ONNX format enforcing three strict parameters:
* **`nms=False`**: Strips the standard Non-Maximum Suppression and box-anchoring layers from the end of the network. This allows the Hailo compiler to inject its own hardware-accelerated NMS features directly onto the NPU nodes.
* **`opset=11`**: Restricts mathematical operators to a standardized set, guaranteeing 100% compatibility with Hailo's translation layers.
* **`batch=1`**: Locks the tensor dimensions for real-time, single-frame edge streaming to maximize processing efficiency.

#### Calibration Dataset Processing
To prevent geometric distortions that degrade 8-bit quantization accuracy, exactly 1024 representative images must be extracted and transformed:
1. Parse the dataset and verify file integrity to discard corrupted images.
2. Calculate an optimal scaling ratio so the shortest side fully covers the target resolution.
3. Scale the images using high-fidelity LANCZOS interpolation to minimize pixel artifacting.
4. Execute a perfect center-crop to output exact 640x640 dimensions.
5. Save these uniform files into a dedicated calibration directory.

### 4. Hardware Compilation

With the `.onnx` graph and calibration images ready, initialize the Hailo AI SW Suite [6]:

```bash
unzip hailo_ai_sw_suite_<version>.zip
./hailo_ai_sw_suite_docker_run.sh
```

> [!WARNING]
> If the suite fails with an out-of-memory error, create a `.wslconfig` file in `C:\Users\<Your_Windows_Username>\.wslconfig` setting `memory=18GB` and `swap=12GB`, then run `wsl --shutdown` and retry.

Once the Docker container launches, place your `.onnx` file and calibration folder into the `shared_with_docker` directory. Execute the compiler using the appropriate parameters for your target chip:

```bash
hailomz compile \
    --ckpt shared_with_docker/<ONNX_MODEL>.onnx \
    --calib-path shared_with_docker/<PATH_TO_CALIB_FOLDER> \
    --yaml workspace/hailo_model_zoo/hailo_model_zoo/cfg/networks/yolov8n.yaml \
    --classes <NUMBER_OF_CLASSES> \
    --hw-arch <hailo8 OR hailo8l>
```

#### Compilation Parameters:
* **`--ckpt`**: The structural baseline for compilation (your ONNX file).
* **`--calib-path`**: The 1024 processed images used to calculate the dynamic range profile, minimizing precision drops when casting tensors from FP32 to INT8.
* **`--yaml`**: The foundational network setup script from the Model Zoo detailing layer-specific optimization rules and pre-processing configurations.
* **`--classes`**: The integer total of unique detection categories evaluated by the model, forcing the prediction heads to scale correctly.
* **`--hw-arch`**: Instructs the scheduling compiler how to partition weight blocks, loop controls, and memory across the physical edge silicon.

---

## Part 2: Inference Phase

This phase is executed directly on the Edge Device (Raspberry Pi equipped with the AI HAT+ and Pi Camera Module).

### 1. System Preparation
Ensure the Raspberry Pi's core software and firmware are fully updated to support the NPU integration:

```bash
sudo apt update && sudo apt full-upgrade
sudo rpi-eeprom-update -a
sudo reboot
```

### 2. NPU Dependency Installation
Install the required software stack that allows the operating system to interface with the Hailo module:

```bash
sudo apt install hailo-all
sudo reboot
```

### 3. Hardware Verification
Once rebooted, query the firmware control to confirm the Hailo-8/8L NPU is actively recognized by the PCIe interface:

```bash
hailortcli fw-control identify
```

A successful connection will return hardware telemetry, including the Board Name and Device Architecture. 

> [!NOTE]
> Receiving "N/A" for the Serial Number, Part Number, and Product Name is standard behavior for the AI HAT+.

### 4. Sensor Integration

Before testing the camera, ensure the physical camera module is connected and configured. For detailed steps, see the [Pi Camera Module 3 Installation Guide](picamera.md).

Verify that the image pipeline is functioning correctly by triggering the camera sensor for a 10-second test stream:

```bash
sudo rpicam-hello -t 10s
```

With the NPU recognized and the camera operational, the system is fully prepared to execute real-time inference using the `.hef` file generated during the compilation phase.

### 5. Run Demos (Optional)

You can try out sample demos by visiting `AI Kit and AI HAT+ software` [7].

---

## Getting Started with RPi 5 and Hailo-8/8L [8]

### Verify Installation

After hardware installation, check if the Hailo chip is recognized by the system:

```bash
hailortcli fw-control identify
```

If everything is OK, it should output something like this:

```text
Executing on device: 0000:01:00.0
Identifying board
Control Protocol Version: 2
Firmware Version: 4.17.0 (release,app,extended context switch buffer)
Logger Version: 0
Board Name: Hailo-8
Device Architecture: HAILO8L
Serial Number: N/A
Part Number: N/A
Product Name: N/A
```

Getting `N/A` for Serial Number, Part Number, and Product Name is normal for the AI HAT+.

Test TAPPAS Core installation by running the following commands:

**Hailotools** (TAPPAS GStreamer elements):

```bash
gst-inspect-1.0 hailotools
```

Expected result:

```text
Plugin Details:
  Name                     hailotools
  Description              hailo tools plugin
  Filename                 /lib/aarch64-linux-gnu/gstreamer-1.0/libgsthailotools.so
  Version                  3.28.2
  License                  unknown
  Source module            gst-hailo-tools
  Binary package           gst-hailo-tools
  Origin URL               https://hailo.ai/

  hailoaggregator: hailoaggregator - Cascading
  hailocounter: hailocounter - postprocessing element
  hailocropper: hailocropper
  hailoexportfile: hailoexportfile - export element
  hailoexportzmq: hailoexportzmq - export element
  hailofilter: hailofilter - postprocessing element
  hailogallery: Hailo gallery element
  hailograytonv12: hailograytonv12 - postprocessing element
  hailoimportzmq: hailoimportzmq - import element
  hailomuxer: Muxer pipeline merging
  hailonv12togray: hailonv12togray - postprocessing element
  hailonvalve: HailoNValve element
```

**Hailonet** (HailoRT inference GStreamer element):

```bash
gst-inspect-1.0 hailo
```

Expected result:

```text
Plugin Details:
  Name                     hailo
  Description              hailo gstreamer plugin
  Filename                 /lib/aarch64-linux-gnu/gstreamer-1.0/libgsthailo.so
  Version                  1.0
  License                  unknown
  Source module            hailo
  Binary package           GStreamer
  Origin URL               http://gstreamer.net/

  hailodevicestats: hailodevicestats element
  hailonet: hailonet element
  synchailonet: sync hailonet element

  3 features:
  +-- 3 elements
```

If `hailo` or `hailotools` are not found, try deleting the GStreamer registry:

```bash
rm ~/.cache/gstreamer-1.0/registry.aarch64.bin
```

### Hailo RPi5 Basic Pipelines [9]

Clone the Repository:

```bash
git clone https://github.com/hailo-ai/hailo-rpi5-examples.git
```

Navigate to the repository directory:

```bash
cd hailo-rpi5-examples
```

Run the following script to automate the installation process:

```bash
./install.sh
```

### Running the examples

When opening a new terminal session, ensure you have sourced the environment setup script:

```bash
source setup_env.sh
```

#### Detection Example

Run the **simple detection** example:

```bash
python basic_pipelines/detection_simple.py
```

To close the application, press `Ctrl+C`.

Run the **full detection** example:

```bash
python basic_pipelines/detection.py
```

To close the application, press `Ctrl+C`.

Running with Raspberry **Pi Camera input**:

```bash
python basic_pipelines/detection.py --input rpi
```

#### Pose Estimation Example

Run the pose estimation example:

```bash
python basic_pipelines/pose_estimation.py
```

To close the application, press `Ctrl+C`. See Detection Example above for additional input options examples.

#### Instance Segmentation Example

Run the instance segmentation example:

```bash
python basic_pipelines/instance_segmentation.py
```

To close the application, press `Ctrl+C`. See Detection Example above for additional input options examples.

#### Depth Estimation Example

Run the depth estimation example:

```bash
python basic_pipelines/depth.py
```

To close the application, press `Ctrl+C`. See Detection Example above for additional input options examples.

---

## References

* [1] LukeDitria/RasPi_YOLO Repository: <https://github.com/LukeDitria/RasPi_YOLO>
* [2] Hailo Documentation - Hailo Software Suite 2025-04: <https://hailo.ai/developer-zone/documentation/hailo-sw-suite-2025-04/?sp_referrer=suite/suite_install.html#docker-installation>
* [3] Raspberry Pi AI HAT+ Documentation: <https://www.raspberrypi.com/documentation/accessories/ai-hat-plus.html>
* [4] NVIDIA Documentation - NVIDIA CUDA Downloads: <https://developer.nvidia.com/cuda-downloads?target_os=Linux&target_arch=x86_64&Distribution=WSL-Ubuntu&target_version=2.0&target_type=deb_local>
* [5] Docker Documentation - Docker Engine Installation: <https://docs.docker.com/engine/install/ubuntu/>
* [6] Hailo Software Downloads: <https://hailo.ai/developer-zone/sw-downloads/>
* [7] AI Kit and AI HAT+ software: <https://www.raspberrypi.com/documentation/computers/ai.html>
* [8] Hailo Documentation - Getting started with RPI5-Hailo8L: <https://community.hailo.ai/t/getting-started-with-rpi5-hailo8l/740>
* [9] Hailo RPi5 Examples Repository: <https://github.com/hailo-ai/hailo-rpi5-examples?tab=readme-ov-file>

[1]: https://github.com/LukeDitria/RasPi_YOLO
[2]: https://hailo.ai/developer-zone/documentation/hailo-sw-suite-2025-04/?sp_referrer=suite/suite_install.html#docker-installation
[3]: https://www.raspberrypi.com/documentation/accessories/ai-hat-plus.html
[4]: https://developer.nvidia.com/cuda-downloads?target_os=Linux&target_arch=x86_64&Distribution=WSL-Ubuntu&target_version=2.0&target_type=deb_local
[5]: https://docs.docker.com/engine/install/ubuntu/
[6]: https://hailo.ai/developer-zone/sw-downloads/
[7]: https://www.raspberrypi.com/documentation/computers/ai.html
[8]: https://community.hailo.ai/t/getting-started-with-rpi5-hailo8l/740
[9]: https://github.com/hailo-ai/hailo-rpi5-examples?tab=readme-ov-file
