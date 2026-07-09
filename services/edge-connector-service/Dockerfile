# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY services/edge-connector-service/requirements.txt /tmp/req.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/req.txt
COPY shared/ /app/shared/
COPY services/edge-connector-service/app/ /app/app/
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
EXPOSE 50053
CMD ["python", "app/main.py"]
