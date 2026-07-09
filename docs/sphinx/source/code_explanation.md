# Codebase Structure and Explanation

This section provides a detailed walk-through of the **AURA Platform** codebase structure. It highlights the main directories, microservices, files, and classes to help developers navigate the project.

---

## High-Level Repository Layout

AURA is architected as a set of loosely coupled microservices communicating via **gRPC** internally, with an independent Python **Edge Agent** and a Next.js frontend web dashboard.

```
AURA/
├── .env.example                # Global template for environment variables
├── docker-compose.yml          # Container orchestration file for server stack & infra
├── README.md                   # Unified project overview, quick start, running guide, and developer guide
├── docs/                       # Project documentation
├── data/                       # Local data storage (models, datasets, scripts, and device configurations)
├── services/                   # Server backend microservices (gRPC/REST/MQTT listeners)
├── edge-runtime/               # Python-based agent code running on edge devices
├── frontend/                   # Next.js 15 frontend application (App Router)
├── shared/                     # Shared modules, utility code, and generated gRPC stubs
├── hardware/                   # Physical device drivers, sensor/actuator libraries, and hw_arch compilation configs
└── others/                     # Boilerplate for other devices / peripherals
```

### `services/api-gateway/` 
Acts as the single REST entry point. Resolves authentication, maps routes, and proxies requests to internal gRPC endpoints.

| File / Component | Folder | Description |
|---|---|---|
| [main.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/api-gateway/app/main.py) | `services/api-gateway/app` | Initializes the FastAPI application, mounts CORS configurations, and binds REST routers. |
| [config.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/api-gateway/app/config.py) | `services/api-gateway/app` | Declares and validates configuration parameters (ports, hosts, JWT secrets). |
| [stubs.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/api-gateway/app/stubs.py) | `services/api-gateway/app` | Implements cached gRPC channel stubs singleton connection pool. |
| [jwt.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/api-gateway/app/auth/jwt.py) | `services/api-gateway/app/auth` | Implements JWT token signing, verification, and mock user validation. |
| [datasets.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/api-gateway/app/routers/datasets.py) | `services/api-gateway/app/routers` | Handles dataset zip validation and S3 uploads. |
| [deployments.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/api-gateway/app/routers/deployments.py) | `services/api-gateway/app/routers` | Manages OTA deployment lifecycle and triggers. |
| [devices.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/api-gateway/app/routers/devices.py) | `services/api-gateway/app/routers` | Manages device registration and queries peripheral catalogs. |
| [models.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/api-gateway/app/routers/models.py) | `services/api-gateway/app/routers` | Handles ML model uploads and compiler activation. |
| [monitoring.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/api-gateway/app/routers/monitoring.py) | `services/api-gateway/app/routers` | Establishes telemetry queries and historical inference endpoints. |
| [scripts.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/api-gateway/app/routers/scripts.py) | `services/api-gateway/app/routers` | Handles user-defined inference scripts registration. |

### `services/registry-service/`
Acts as the metadata catalog. Persists data about registered hardware, uploaded model assets, and scripts.

| File / Component | Folder | Description |
|---|---|---|
| [main.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/registry-service/app/main.py) | `services/registry-service/app` | Instantiates and starts the registry service gRPC listener on port `50051`. |
| [config.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/registry-service/app/config.py) | `services/registry-service/app` | Service settings loader. |
| [update_existing_datasets.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/registry-service/app/update_existing_datasets.py) | `services/registry-service/app` | Migration scripts to bootstrap database datasets logic. |
| [ai_handler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/registry-service/app/grpc_handlers/ai_handler.py) | `services/registry-service/app/grpc_handlers` | Resolves RPCs relating to models registration, dataset files, and compiler reports. |
| [device_handler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/registry-service/app/grpc_handlers/device_handler.py) | `services/registry-service/app/grpc_handlers` | Resolves RPCs relating to device registrations, updates, and deletes. |
| [script_handler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/registry-service/app/grpc_handlers/script_handler.py) | `services/registry-service/app/grpc_handlers` | Resolves RPCs relating to script file catalog storage. |
| [devices.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/registry-service/app/repositories/devices.py) | `services/registry-service/app/repositories` | PostgreSQL DB queries interface for device records. |
| [models.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/registry-service/app/repositories/models.py) | `services/registry-service/app/repositories` | PostgreSQL DB queries interface for models and datasets records. |
| [scripts.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/registry-service/app/repositories/scripts.py) | `services/registry-service/app/repositories` | PostgreSQL DB queries interface for scripts metadata. |
| [orm.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/registry-service/app/models/orm.py) | `services/registry-service/app/models` | SQLAlchemy ORM classes mapping database tables (`devices`, `models`, `scripts`, `deployments`). |

### `services/mlops-service/`
Runs asynchronous compilation and optimization pipelines using isolated Docker runtimes.

| File / Component | Folder | Description |
|---|---|---|
| [main.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/mlops-service/app/main.py) | `services/mlops-service/app` | Starts the gRPC compilation listener server on port `50052`. |
| [config.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/mlops-service/app/config.py) | `services/mlops-service/app` | MLOps environmental parameters validation settings. |
| [worker.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/mlops-service/app/worker.py) | `services/mlops-service/app` | ARQ Redis worker processing compiled models and yolo training runs. |
| [compilation_handler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/mlops-service/app/grpc_handlers/compilation_handler.py) | `services/mlops-service/app/grpc_handlers` | Listens to and launches job compilation requests. |
| [base.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/mlops-service/app/compilers/base.py) | `services/mlops-service/app/compilers` | Defines abstract `CompilerBase` interface and Redis logs streamer tools. |
| [yolo_train.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/mlops-service/app/compilers/yolo_train.py) | `services/mlops-service/app/compilers` | Pipeline trigger that executes YOLOv8 model training. |

### `services/edge-connector-service/`
Connects the cloud services to the physical hardware devices.

| File / Component | Folder | Description |
|---|---|---|
| [main.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/edge-connector-service/app/main.py) | `services/edge-connector-service/app` | Entry point starting the gRPC connector server on port `50053` and the Prometheus metrics exporter on port `9100`. |
| [config.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/edge-connector-service/app/config.py) | `services/edge-connector-service/app` | Service database and broker credentials validation. |
| [worker.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/edge-connector-service/app/worker.py) | `services/edge-connector-service/app` | ARQ queue worker monitoring active deployments status. |
| [deployment_handler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/edge-connector-service/app/grpc_handlers/deployment_handler.py) | `services/edge-connector-service/app/grpc_handlers` | Handles RPCs for scheduling OTA deployments. |
| [monitoring_handler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/edge-connector-service/app/grpc_handlers/monitoring_handler.py) | `services/edge-connector-service/app/grpc_handlers` | Handles RPC queries retrieving active telemetry statuses. |
| [listener.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/edge-connector-service/app/mqtt/listener.py) | `services/edge-connector-service/app/mqtt` | MQTT loop client ingesting telemetry, acknowledgements, and inference payloads. |
| [orm.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/edge-connector-service/app/models/orm.py) | `services/edge-connector-service/app/models` | SQLAlchemy structures tracking active deployments. |
| [mongo.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/edge-connector-service/app/models/mongo.py) | `services/edge-connector-service/app/models` | Time-series metrics document structures. |
| [deployments.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/edge-connector-service/app/repositories/deployments.py) | `services/edge-connector-service/app/repositories` | Query interface for deployment statuses. |
| [monitoring.py](https://github.com/Estelamb/TFM_MIoT/blob/main/services/edge-connector-service/app/repositories/monitoring.py) | `services/edge-connector-service/app/repositories` | Ingest log controller inserting states to MongoDB and updating Prometheus gauges. |

---

## 2. Edge Agent (`edge-runtime/`)

Designed to run locally on the physical target computer (e.g., Raspberry Pi 5).

| File / Component | Folder | Description |
|---|---|---|
| [agent.py](https://github.com/Estelamb/TFM_MIoT/blob/main/edge-runtime/agent.py) | `edge-runtime` | Main client entrypoint launching MQTT subscriptions, periodic telemetry updates, and active inference runtime loops. |
| [hardware_daemon.py](https://github.com/Estelamb/TFM_MIoT/blob/main/edge-runtime/hardware_daemon.py) | `edge-runtime` | Host-level HTTP server exposing cameras and accelerators natively to Docker containers. |
| [detect.py](https://github.com/Estelamb/TFM_MIoT/blob/main/edge-runtime/aura_hw/detect.py) | `edge-runtime/aura_hw` | Probes host system hardware to detect connected accelerators (Hailo, IMX500, CPU). |
| [device_manager.py](https://github.com/Estelamb/TFM_MIoT/blob/main/edge-runtime/aura_hw/device_manager.py) | `edge-runtime/aura_hw` | Controls dynamic sensor configuration and peripheral drivers instantiation. |
| [loader.py](https://github.com/Estelamb/TFM_MIoT/blob/main/edge-runtime/aura_hw/loader.py) | `edge-runtime/aura_hw` | Dynamically compiles and loads the user's inference script in memory. |
| [runtime.py](https://github.com/Estelamb/TFM_MIoT/blob/main/edge-runtime/aura_hw/runtime.py) | `edge-runtime/aura_hw` | Public hardware interfaces managing model execution backends. |
| [comm_client.py](https://github.com/Estelamb/TFM_MIoT/blob/main/edge-runtime/pal/comm_client.py) | `edge-runtime/pal` | Stable MQTT wrapper client mapping telemetry payload conventions. |
| [orchestrator.py](https://github.com/Estelamb/TFM_MIoT/blob/main/edge-runtime/pal/orchestrator.py) | `edge-runtime/pal` | Handles parallel telemetry metrics and inference loops execution. |
| [ota_handler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/edge-runtime/pal/ota_handler.py) | `edge-runtime/pal` | Manages secure HTTP downloads of model files and executes SHA-256 integrity validation checks. |

---

## 3. Frontend Web Dashboard (`frontend/`)

Built using **Next.js 16** (TypeScript, Tailwind CSS, TanStack Query).

* **`frontend/app/`**: App Router page components:
  * `layout.tsx` & `page.tsx`: Welcome dashboard and main navigation.
  * **`(app)/devices/`**: Displays registered edge devices and live connections.
  * **`(app)/models/`**: Manages model uploads and monitors active compilations.
  * **`(app)/scripts/`**: Repository for inference Python scripts.
  * **`(app)/deployments/`**: Form to configure and deploy assets OTA.
  * **`(app)/monitoring/`**: Graphic charts powered by WebSockets to monitor resources and inference frames in real time.
* **`frontend/components/`**: Modular UI elements (resource charts, modal windows, table views).
* **`frontend/hooks/`**: Custom React hooks handling state updates and WebSocket bindings.
* **`frontend/lib/`**: Axios client utility functions.

---

## 4. Shared Modules (`shared/`)

Common modules imported by both backend microservices and edge runtimes.

| File / Component | Folder | Description |
|---|---|---|
| [proto_gen/](https://github.com/Estelamb/TFM_MIoT/blob/main/shared/proto_gen) | `shared` | Generated Protocol Buffer Python message stubs and services bindings. |
| [base.py](https://github.com/Estelamb/TFM_MIoT/blob/main/shared/transport/base.py) | `shared/transport` | Defines abstract transport layers interfaces. |
| [mqtt.py](https://github.com/Estelamb/TFM_MIoT/blob/main/shared/transport/mqtt.py) | `shared/transport` | Reusable MQTT connection and publish wrappers logic. |
| [database.py](https://github.com/Estelamb/TFM_MIoT/blob/main/shared/utils/database.py) | `shared/utils` | Shared SQLAlchemy engine connection context helpers. |
| [minio.py](https://github.com/Estelamb/TFM_MIoT/blob/main/shared/utils/minio.py) | `shared/utils` | Wraps client logic for presigned URL signatures and uploads. |
| [logging.py](https://github.com/Estelamb/TFM_MIoT/blob/main/shared/utils/logging.py) | `shared/utils` | Unified format configuration settings for all console outputs. |
| [grpc_server.py](https://github.com/Estelamb/TFM_MIoT/blob/main/shared/utils/grpc_server.py) | `shared/utils` | Core listener startup helper wrapping standard gRPC parameters. |

---

## 5. Physical Hardware Integration (`hardware/`)

Driver bindings and compilation workflows connecting deep learning accelerators and sensor peripherals to the AURA Agent.

### Driver system

| File / Component | Folder | Description |
|---|---|---|
| [utils.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/utils.py) | `hardware` | Shared utilities resolving active hardware configurations and loading target-specific library modules. |

### Hardware architecture backends (`hw_arch/`)

| Target | `compilation/compiler.py` | `inference/library.py` |
|---|---|---|
| `hailo8` | [compiler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/hw_arch/hailo8/compilation/compiler.py) | [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/hw_arch/hailo8/inference/library.py) |
| `hailo8l` | [compiler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/hw_arch/hailo8l/compilation/compiler.py) | [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/hw_arch/hailo8l/inference/library.py) |
| `rpi` | [compiler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/hw_arch/rpi/compilation/compiler.py) | [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/hw_arch/rpi/inference/library.py) |
| `rpi_ai_cam` | [compiler.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/hw_arch/rpi_ai_cam/compilation/compiler.py) | [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/hw_arch/rpi_ai_cam/inference/library.py) |

### Sensors

| File / Component | Folder | Description |
|---|---|---|
| [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/sensors/camera/imx500/library.py) | `hardware/sensors/camera/imx500` | Sony IMX500 camera capture driver interface mapping on-sensor metadata structures. |
| [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/sensors/camera/rpi_camera_module_3/library.py) | `hardware/sensors/camera/rpi_camera_module_3` | Standard Raspberry Pi Camera Module 3 driver using `picamera2`. |
| [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/sensors/gps/gps_simulated/library.py) | `hardware/sensors/gps/gps_simulated` | Simulated GPS receiver serial parser feed for hardware testing. |
| [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/sensors/template/library.py) | `hardware/sensors/template` | Reference skeleton implementing generic sensor category models. |

### Actuators

| File / Component | Folder | Description |
|---|---|---|
| [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/actuators/template/dummy_actuator/library.py) | `hardware/actuators/template/dummy_actuator` | No-op actuator module stub handling testing logs output. |
| [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/actuators/template/library.py) | `hardware/actuators/template` | Reference skeleton implementing generic actuator category models. |

### Others

| File / Component | Folder | Description |
|---|---|---|
| [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/others/template/dummy_other/library.py) | `hardware/others/template/dummy_other` | No-op peripheral device stub used for integration testing. |
| [library.py](https://github.com/Estelamb/TFM_MIoT/blob/main/hardware/others/template/library.py) | `hardware/others/template` | Reference skeleton implementing general custom device categories. |

---

## 6. Local Data Storage (`data/`)

The `data/` directory is used for data samples to use within the platform.

* **`data/edge-configs/`**: Device-specific configuration templates (containing `components_config.yaml` and `device_config.yaml`) for Hailo-8, Hailo-8L, Raspberry Pi AI Camera, and Raspberry Pi CPU setups.
* **`data/models/`**: Stores YOLO model weights (like `drowsiness_v8.pt` and `forgotten_v8.pt`).
* **`data/scripts/`**: Default user-defined inference scripts (like `camera_infer.py` and `child_object_detection.py`) that are deployed OTA to edge devices.
