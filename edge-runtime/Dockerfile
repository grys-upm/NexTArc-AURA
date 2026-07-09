FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# ── PAL-only dependencies (no hardware-specific packages) ────────────────────
RUN pip install --no-cache-dir \
    aiomqtt==2.3.0 \
    httpx==0.27.2 \
    numpy \
    psutil==6.0.0 \
    pyyaml>=6.0 \
    "onnxruntime>=1.16.0" \
    "opencv-python-headless"

# ── Application source (PAL + dynamic loading framework) ─────────────────────
COPY edge-runtime/aura_hw/   /app/aura_hw/
COPY edge-runtime/pal/       /app/pal/
COPY edge-runtime/config/    /app/config/
COPY edge-runtime/agent.py   /app/agent.py

# ── Hardware backend directory (empty at build time) ─────────────────────────
# Populated at runtime via OTA (update_libraries command) when the device
# connects to the AURA platform.
RUN mkdir -p /app/hardware

# ── Runtime environment ──────────────────────────────────────────────────────
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    AURA_DEVICE_ID=dev-device-001 \
    AURA_MQTT_HOST=mosquitto \
    AURA_WORK_DIR=/tmp/aura \
    AURA_LOG_LEVEL=INFO

CMD ["python", "agent.py"]
