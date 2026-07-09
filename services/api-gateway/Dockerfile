# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY services/api-gateway/requirements.txt /tmp/req.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install -r /tmp/req.txt
COPY shared/ /app/shared/
COPY services/api-gateway/app/ /app/app/
ENV PYTHONPATH=/app PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
