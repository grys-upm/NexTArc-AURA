# Architecture

## Service topology

The following diagram illustrates how components communicate across the AURA platform:

```
    Frontend (Next.js :3000)
              │
              │ HTTP + JWT REST & WebSockets
              ▼
     API Gateway (:8000)
              │
              ├─▶ (gRPC :50051) ── registry-service ── [PostgreSQL, MinIO]
              ├─▶ (gRPC :50052) ── mlops-service    ── [MinIO, Docker Socket, Redis]
              └─▶ (gRPC :50053) ── edge-connector-service ── [PostgreSQL, MongoDB, MinIO, Prometheus]
                                           ▲
                                           │ gRPC / events
                                           ▼
                                    MQTT Broker (:1883)
                                           ▲
                                           │ MQTT (Commands with presigned URLs & SHA-256)
                                           ▼
                                    Edge Runtime (PAL) ◀──(Direct HTTPS Download)── MinIO
```

---

## gRPC Internal Communication

All downstream microservices within the AURA backend communicate internally using **gRPC** over HTTP/2. The **API Gateway** acts as a reverse proxy, translating frontend REST HTTP requests into gRPC calls and routing them to the appropriate services:

- **Registry Service (`:50051`)**: Exposes RPCs for managing catalog metadata for devices, models, and scripts.
- **MLOps Service (`:50052`)**: Handles asynchronous machine learning model compilation and YOLOv8 training.
- **Edge Connector Service (`:50053`)**: Manages device connection states, metrics ingestion, OTA deployment status, and MQTT event coordination.

Protocol buffers definitions reside under `shared/proto`, and the compiled stubs are dynamically loaded from `shared/proto_gen`.

---

## MQTT topics

Perimetral edge devices communicate asynchronously with the **Edge Connector Service** via the MQTT broker using the following topics structure:

| Topic | Direction | Purpose |
|---|---|---|
| `device/{id}/commands` | Cloud → Edge | Send deploy/update commands |
| `device/{id}/events` | Edge → Cloud | Acknowledge deploy or report failure |
| `device/{id}/telemetry` | Edge → Cloud | CPU, RAM, active model ID |
| `device/{id}/inference` | Edge → Cloud | Inference results (JSON) |

> [!NOTE]
> **Privacy & Anonymity**: The `device/{id}/inference` topic only transmits structured, high-level JSON payloads. Raw images, video feeds, or any personally identifiable information are never published or uploaded, preserving anonymity.

---

## Database layout

The platform uses a specialized database stack adapted for relational metadata, binary storage, and time-series telemetry:

- **PostgreSQL** — Relational metadata: Persists structured definitions of `devices`, `models`, `scripts`, and `deployments`.
- **MongoDB** — Time-series storage: Ingests rapid, append-only `inference_results` and keeps the latest `device_states` from edge device telemetry.
- **Redis** — Job queuing & state caching: Manages background async jobs queue (using `arq` workers) for compiler tasks, training execution, and coordination of deployment cancellations.
- **Prometheus** — Telemetry metrics: Gathers and exposes node exporter metrics and edge agent statistics for visualization.
- **MinIO** — Object storage: Stores raw uploaded PyTorch `.pt` files under `models/`, compiled binaries (like `.hef` or `.onnx`) under `compiled/`, raw ZIP datasets under `datasets/`, and custom user-provided inference scripts under `scripts/`.

---

## API Gateway REST API

The API Gateway exposes REST HTTP endpoints to the frontend, requiring authentication via JWT:

- **Authentication**:
  - `POST /auth/token`: Authenticate admin credentials and generate JWT tokens.
- **Devices Management**:
  - `GET /api/devices`: Retrieve all registered devices.
  - `POST /api/devices`: Register a new device.
  - `GET /api/devices/{device_id}`: Retrieve a single device detail.
  - `PUT /api/devices/{device_id}`: Update device details.
  - `DELETE /api/devices/{device_id}`: Remove a device registry.
  - `GET /api/devices/hardware-types`: Query supported hardware accelerators.
  - `GET /api/devices/sensors`: Query supported sensors drivers.
  - `GET /api/devices/actuators`: Query supported actuators.
  - `GET /api/devices/labels`: Query a dictionary mapping hardware keys to friendly labels.
- **Models & Datasets Management**:
  - `GET /api/models`: List registered ML models.
  - `POST /api/models`: Upload a new ML model `.pt` file.
  - `DELETE /api/models/{model_id}`: Delete an ML model.
  - `POST /api/models/{model_id}/compile`: Trigger a compilation job for a specific hardware target.
  - `GET /api/datasets`: List available datasets.
  - `POST /api/datasets`: Register and upload a dataset ZIP.
  - `DELETE /api/datasets/{dataset_id}`: Delete a dataset.
- **Scripts Management**:
  - `GET /api/scripts`: List user-defined inference scripts.
  - `POST /api/scripts`: Upload/register a new `.py` inference script.
  - `DELETE /api/scripts/{script_id}`: Delete a script.
- **Deployments Management**:
  - `GET /api/deployments`: List all deployments.
  - `POST /api/deployments`: Trigger an OTA deployment of a model + script to a device.
  - `GET /api/deployments/device/{device_id}`: Get deployments for a specific device.
  - `DELETE /api/deployments/{deployment_id}`: Cancel/delete an active deployment.
- **Telemetry & Monitoring**:
  - `GET /api/monitoring/devices`: Get real-time statuses and hardware metrics for all devices.
  - `GET /api/monitoring/devices/{device_id}`: Get active state of a specific device.
  - `GET /api/monitoring/devices/{device_id}/inference`: Retrieve latest historical inference payloads.