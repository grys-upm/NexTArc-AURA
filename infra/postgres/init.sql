-- =============================================================================
-- AURA Platform PoC — Schema
-- =============================================================================
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Dispositivos edge
CREATE TABLE IF NOT EXISTS devices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    hardware_type   TEXT NOT NULL,  -- hailo8 | hailo8l | rpi_ai_cam | rpi | jetson_orin_nano
    description     TEXT,
    status          TEXT NOT NULL DEFAULT 'offline',  -- online | offline
    last_seen_at    TIMESTAMPTZ,
    others          TEXT[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Modelos subidos (pt original + compilado)
CREATE TABLE IF NOT EXISTS datasets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT,
    object_key      TEXT,
    sha256          TEXT,
    size_bytes      BIGINT,
    meta_info       JSON,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dataset_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id      UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    version         TEXT NOT NULL,
    description     TEXT,
    object_key      TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    size_bytes      BIGINT NOT NULL,
    meta_info       JSON,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS models (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT,
    source_key      TEXT NOT NULL,       -- MinIO: models/<id>/source.pt
    source_sha256   TEXT NOT NULL,
    compiled_key    TEXT,                -- MinIO: compiled/<id>/model.hef  (null hasta compilar)
    compiled_sha256 TEXT,
    hardware_type   TEXT,                -- para qué hw está compilado
    compile_status  TEXT NOT NULL DEFAULT 'pending',  -- pending | compiling | ready | failed
    compile_error   TEXT,
    dataset_id      UUID REFERENCES datasets(id) ON DELETE SET NULL,
    dataset_version_id UUID REFERENCES dataset_versions(id) ON DELETE SET NULL,
    base_architecture TEXT,
    epochs          INT,
    input_size      TEXT,
    batch_size      INT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Scripts (pre/post inference)
CREATE TABLE IF NOT EXISTS scripts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    description     TEXT,
    script_key      TEXT NOT NULL,       -- MinIO: scripts/<id>/script.py
    script_sha256   TEXT NOT NULL,
    language        TEXT NOT NULL,       -- python | c++ | java
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Despliegues
CREATE TABLE IF NOT EXISTS deployments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_id       UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    model_id        UUID NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    script_id       UUID NOT NULL REFERENCES scripts(id) ON DELETE CASCADE,
    name            TEXT,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | running | failed
    sent_at         TIMESTAMPTZ,
    running_at      TIMESTAMPTZ,
    error_msg       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_deployments_device ON deployments(device_id);
CREATE INDEX IF NOT EXISTS idx_deployments_status ON deployments(status);
CREATE INDEX IF NOT EXISTS idx_models_compile_status ON models(compile_status);

CREATE TABLE IF NOT EXISTS model_compilations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id        UUID NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    hardware_type   TEXT NOT NULL,
    compiled_key    TEXT NOT NULL,
    compiled_sha256 TEXT NOT NULL,
    compile_status  TEXT NOT NULL DEFAULT 'pending',
    compile_error   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(model_id, hardware_type)
);

CREATE INDEX IF NOT EXISTS idx_model_compilations_model ON model_compilations(model_id);
CREATE INDEX IF NOT EXISTS idx_model_compilations_hw ON model_compilations(hardware_type);
