# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev libgl1 libglib2.0-0 libxcb1 libx11-xcb1 docker-cli && rm -rf /var/lib/apt/lists/*
COPY services/mlops-service/requirements.txt /tmp/req.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/req.txt
COPY shared/ /app/shared/
COPY services/mlops-service/app/ /app/app/
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
EXPOSE 50052
CMD ["python", "app/main.py"]
