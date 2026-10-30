-- Initial schema. Spec: specs/07-api-and-data.md#database-h2-file-mode-flyway-migrations
-- JSON documents (render_job.log, render_job.edit_plan, style_preset.defaults) are stored as CLOB.

CREATE TABLE project (
    id         UUID PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE asset (
    id              UUID PRIMARY KEY,
    project_id      UUID NOT NULL,
    type            VARCHAR(16) NOT NULL,
    filename        VARCHAR(512) NOT NULL,
    path            VARCHAR(1024) NOT NULL,
    file_hash       VARCHAR(64),
    size_bytes      BIGINT NOT NULL,
    duration_sec    DOUBLE PRECISION,
    width           INT,
    height          INT,
    fps             DOUBLE PRECISION,
    camera_mode     VARCHAR(32),
    log_profile     VARCHAR(32),
    analysis_status VARCHAR(16) NOT NULL,
    analysis_path   VARCHAR(1024),
    created_at      TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT fk_asset_project FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE,
    CONSTRAINT ck_asset_type CHECK (type IN ('VIDEO', 'PHOTO', 'MUSIC')),
    CONSTRAINT ck_asset_analysis_status
        CHECK (analysis_status IN ('PENDING', 'RUNNING', 'DONE', 'FAILED'))
);

CREATE INDEX ix_asset_project ON asset (project_id);

CREATE TABLE render_job (
    id           UUID PRIMARY KEY,
    project_id   UUID NOT NULL,
    ratio        VARCHAR(8) NOT NULL,
    quality      VARCHAR(8) NOT NULL,
    fps          INT NOT NULL,
    style        VARCHAR(32) NOT NULL,
    mode         VARCHAR(16) NOT NULL,
    length_sec   INT,
    prompt       CLOB,
    cool_mode    BOOLEAN NOT NULL,
    seed         BIGINT NOT NULL,
    status       VARCHAR(16) NOT NULL,
    stage        VARCHAR(32),
    progress     INT NOT NULL,
    log          CLOB,
    edit_plan    CLOB,
    preview_path VARCHAR(1024),
    output_path  VARCHAR(1024),
    error        VARCHAR(2048),
    created_at   TIMESTAMP WITH TIME ZONE NOT NULL,
    finished_at  TIMESTAMP WITH TIME ZONE,
    CONSTRAINT fk_render_job_project
        FOREIGN KEY (project_id) REFERENCES project (id) ON DELETE CASCADE,
    CONSTRAINT ck_render_job_status CHECK (status IN (
        'QUEUED', 'ANALYZING', 'PLANNING', 'COMPOSING', 'UPSCALING', 'ENCODING',
        'DONE', 'FAILED', 'CANCELLED'))
);

CREATE INDEX ix_render_job_project ON render_job (project_id);

CREATE TABLE job (
    id         UUID PRIMARY KEY,
    kind       VARCHAR(16) NOT NULL,
    ref_id     UUID NOT NULL,
    priority   INT NOT NULL,
    status     VARCHAR(16) NOT NULL,
    attempts   INT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT ck_job_kind CHECK (kind IN ('ANALYZE', 'RENDER')),
    CONSTRAINT ck_job_status CHECK (status IN ('QUEUED', 'RUNNING', 'DONE', 'FAILED'))
);

CREATE INDEX ix_job_queue ON job (status, priority, created_at);

CREATE TABLE style_preset (
    id       VARCHAR(32) PRIMARY KEY,
    name     VARCHAR(64) NOT NULL,
    defaults CLOB NOT NULL
);
