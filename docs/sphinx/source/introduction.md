# Introduction to the AURA Project

Welcome to the official documentation for **AURA Platform**, a comprehensive, end-to-end platform designed to simplify and automate the deployment lifecycle of Machine Learning and Computer Vision models on Internet of Things (IoT) Edge devices.

## What is AURA?

AURA provides a robust and scalable infrastructure that enables ML engineers, developers, and integrators to manage and orchestrate Edge AI workflows with ease. The platform covers the following key phases:

1. **Upload** a trained `.pt` model
2. **Compile** it for your target hardware (Hailo-8, IMX500, ONNX)
3. **Deploy** model + inference script to one or more edge devices over MQTT
4. **Download & verify** the compiled model on the edge device, with SHA-256 checksum validation to guarantee file integrity
5. **Monitor** CPU/RAM telemetry and inference results in real time

---

## System Architecture

The AURA ecosystem is divided into two primary blocks: the **Cloud/Server Platform** and the **IoT Edge Runtime**.

```
                                 +--------------------+
                                 | Frontend Interface |
                                 |   (Next.js App)    |
                                 +---------+----------+
                                           | HTTP / JWT
                                           v
                                 +---------+----------+
                                 |    API Gateway     |
                                 |     (FastAPI)      |
                                 +---------+----------+
                                           |
                +--------------------------+-----------------------------+
                |                          |                             |
           gRPC |                     gRPC |                        gRPC |
                v                          v                             v
    +-----------+------------+   +---------+---------+       +-----------+------------+
    |    registry-service    |   |   mlops-service   |       | edge-connector-service |
    |  (Models/Scripts/Db)   |   |   (Compilation)   |       |                        |
    +-----------+------------+   +---------+---------+       +--+-------------------+-+
                |                          |                    |                   |
     MinIO / PG |                   Docker |               MQTT |                   | Mongo / Prom
                v                          v                    v                   v
    +-----------+------------+   +---------+---------+   +------+------+ +----------+----------+
    |  Storage & Databases   |   |   Docker Socket   |   | MQTT Broker | | Metrics & Telemetry |
    |  (PostgreSQL & MinIO)  |   |                   |   +------+------+ +---------------------+
    +------------------------+   +-------------------+          ^
                |                                               |
                |                    MQTT (Commands, Telemetry) |
                |                                               v 
                |                                        +------+------+
                |   HTTP (Download + SHA-256 Checksum)   |   Device    |
                +--------------------------------------->| Edge Agent  |
                                                         +-------------+
```

---

## Key Components

* **Frontend (Next.js)**: A modern, intuitive dashboard interface for managing devices, uploading model/script artifacts, viewing live logs, and visualizing telemetry charts.
* **API Gateway (FastAPI)**: Centralizes frontend requests, handles JWT authentication, and exposes a clean REST API while routing internal traffic using gRPC.
* **Microservices (gRPC)**:
  * `registry-service`: Manages the database tables and metadata for devices, models, and scripts.
  * `mlops-service`: Orchestrates model compilation by interfacing with Docker sockets to isolate resource-intensive compiling tasks.
  * `edge-connector-service`: Handles communications with edge agents via MQTT, stores inference results in MongoDB, and exposes system telemetry for Prometheus.
* **IoT Edge Runtime**: A Python agent optimized to run on the physical device, responsible for downloading models, verifying files with SHA-256 checksums, and executing inference tasks via the `aura_hw` library.

---

## Supported Hardware

AURA abstracts the complexity of the underlying hardware acceleration. Developers write generic inference scripts, and the platform handles the execution backend routing:

| Device | Model format | Status |
|---|---|---|
| RPi5 + Hailo-8 | `.hef` | ✅ Full |
| RPi5 + Hailo-8L | `.hef` | ✅ Full |
| RPi5 + AI Camera (IMX500) | `packerOut.zip` | ✅ Full |
| RPi5 (CPU) | `.onnx` | ✅ Full |

To start deploying your own models, head over to the [Platform Execution Tutorial](tutorials/run_platform) to set up the system.

---

## Privacy & Anonymity

AURA is designed with privacy-by-design principles to ensure compliance and respect user anonymity. The edge runtime processes video/image input locally on the physical device and only transmits high-level, structured inference results (e.g., class labels, confidence scores, and bounding box coordinates in JSON format) back to the cloud/server platform. Raw camera frames, video files, or any personally identifiable information are never sent over the network, ensuring complete subject anonymity.

