# How to Run the AURA Platform (Server & Edge Agent)

This guide provides a detailed, step-by-step walkthrough to set up and run both the core server services (Backend, Frontend, and Databases) and the local agent running on the perimetral hardware.

---

## 1. Prerequisites

Before starting the installation, ensure your host system or server meets the following requirements:

* **Docker Engine** (version 24 or higher) with **Docker Compose v2**.
* Minimum of **8 GB RAM** (16 GB recommended if compiling heavy models concurrently).
* The following network ports must be free:
  * `3000` (Next.js Frontend)
  * `8000` (API Gateway / Swagger Docs)
  * `1883` (Mosquitto MQTT Broker)
  * `5432` (PostgreSQL)
  * `9000` & `9001` (MinIO S3 Storage server & Admin console)
  * `27017` (MongoDB)
  * `50051–50053` (Internal gRPC ports for service-to-service communication)
  * `9100` (Prometheus metrics exporter)

---

## 2. Setting Up the Server Environment

AURA uses environment variables declared in a `.env` file in the project root to initialize passwords, secrets, and connection URIs.

1. Duplicate the example environment variables template:
   ```bash
   cp .env.example .env
   ```

2. Generate a secure secret key for JWT signing and paste it into the `.env` file:
   ```bash
   # Generate a random hex key
   openssl rand -hex 32
   ```
   Open the `.env` file, locate the `SECRET_KEY` variable, and replace its default value with the generated hex key.

> [!NOTE]
> For local development, the defaults configured in `.env.example` work out of the box without any further modifications.

---

## 3. Starting the Platform Services

To compile the local Docker images and start the full platform stack in the background (detached mode), execute the following command in the project root:

```bash
docker compose up -d
```

* **Note**: The first startup can take between **3 to 5 minutes** since Docker has to download base images and compile containers for each microservice.

Once the command finishes, check the health of all containers:

```bash
docker compose ps
```

You should see all containers (`api-gateway`, `registry-service`, `mlops-service`, `edge-connector-service`, `postgres`, `mongodb`, `mosquitto`, `minio`, and `frontend`) listed in the `Up` or `Running` state.

### Useful Access URLs

| Service | URL / Host | Default Credentials |
|---|---|---|
| **Web Console** | [http://localhost:3000](http://localhost:3000) | Username: `admin` / Password: `aura2026` |
| **API Docs (Swagger)** | [http://localhost:8000/docs](http://localhost:8000/docs) | Requires logging in first at the `/auth/token` endpoint |
| **MinIO Console** | [http://localhost:9001](http://localhost:9001) | Username: `aura` / Password: `aura_dev` |
| **Prometheus Metrics** | [http://localhost:9100/metrics](http://localhost:9100/metrics) | Anonymous access |

---

## 4. Troubleshooting and Logs

If any service fails or behaves unexpectedly, inspect the logs in real time:

```bash
# View combined logs of all containers
docker compose logs -f

# Filter logs for a specific service (e.g., API Gateway)
docker compose logs -f api-gateway

# Filter logs for the edge-connector-service
docker compose logs -f edge-connector-service
```

---

## 5. Running the Edge Agent on a Physical Device

The edge agent runs on the target physical hardware (e.g., Raspberry Pi 5). It connects to the AURA Platform via MQTT to receive deployment commands and report device telemetry.

### Step 1: Copy runtime files to the edge device
Transfer the `edge-runtime/` folder from the project to the local storage of your edge device (using `scp`, `rsync`, or cloning the repository directly on the device).

### Step 2: Install dependencies on the device
The edge agent requires Python 3.10 or higher. Navigate to the runtime folder and install dependencies:

```bash
# Navigate to the runtime folder
cd edge-runtime

# Install required Python packages
pip install -r requirements.txt
```

> [!IMPORTANT]
> If you plan to use accelerators such as the Hailo-8 or the Sony IMX500 AI Camera, make sure that the hardware vendor SDK, firmware, and kernel drivers are installed on the device operating system before starting the agent.

### Step 3: Configure the Environment Variables
Before starting the agent, copy the template `.env.example` to `.env` in the `edge-runtime/` directory:

```bash
cp .env.example .env
```

Open the `.env` file and customize the connection and identifier settings as needed (e.g. `AURA_DEVICE_ID`, `AURA_MQTT_HOST`, `AURA_HARDWARE_TYPE`, etc.).

### Step 4: Run the Edge Runtime Stack
The Edge Runtime is composed of a host-level Hardware Daemon and the containerized Edge Agent. You can automatically build, launch, and run both components using the provided startup scripts:

* **On Linux / macOS**:
  ```bash
  chmod +x run_edge.sh
  ./run_edge.sh
  ```

* **On Windows (PowerShell)**:
  ```powershell
  .\run_edge.ps1
  ```

### Agent Configuration Parameters

| Variable | Default Value | Description |
|---|---|---|
| `AURA_DEVICE_ID` | `dev-device-001` | Unique device identifier. Must exactly match the Device ID registered in the AURA web console. |
| `AURA_MQTT_HOST` | `localhost` | IP address or domain name where the platform's MQTT broker is running. |
| `AURA_MQTT_PORT` | `1883` | MQTT broker port (usually `1883`). |
| `AURA_HARDWARE_TYPE` | *Auto-detected* | Overrides automatic hardware detection. Valid values: `hailo8`, `hailo8l`, `imx500`, `rpi` (CPU). |
| `AURA_TELEMETRY_INTERVAL` | `10` | Frequency in seconds at which the agent sends CPU/RAM telemetry messages. |

The scripts will establish the connection with the broker. Upon success, the device state will change to **Online** in the AURA web dashboard.

---

## Next Steps

Once the platform is running and you have connected your Edge device, proceed to learn how to prepare custom logic and hardware extensions:
* Learn how to write inference scripts for the platform in the [How to Create a Custom Inference Script](create_script.md) tutorial.
* Learn how to expand compilation capabilities or add new peripheral drivers in the [How to Add New Hardware](add_hardware.md) guide.
