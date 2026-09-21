-- Schema for capturing API request/response samples used as unit-test fixtures
-- when migrating SAP PI interfaces to SAP CPI.
-- Safe to re-run: uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS public.api (
    apiname VARCHAR(255) PRIMARY KEY,
    count   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS public.api_request_log_for_migration (
    message_id        VARCHAR(255) PRIMARY KEY,
    api_name          VARCHAR(255) NOT NULL,
    api_version       VARCHAR(50),
    full_url          TEXT,
    resource_path     TEXT,
    http_method       VARCHAR(10),
    content_type      VARCHAR(255),
    client_ip         VARCHAR(64),
    app_name          VARCHAR(255),
    user_id           VARCHAR(255),
    client_id         VARCHAR(255),
    request_headers   TEXT,
    request_data      TEXT,
    request_format    VARCHAR(10),          -- json | xml | form | text | binary | none
    request_time      TIMESTAMP,
    response_headers  TEXT,
    response_data     TEXT,
    response_format   VARCHAR(10),
    response_content_type VARCHAR(255),
    http_status       VARCHAR(10),
    response_time     TIMESTAMP,
    execution_time_ms BIGINT
);

-- Upgrade path for tables created before headers/body were split into separate columns.
ALTER TABLE public.api_request_log_for_migration ADD COLUMN IF NOT EXISTS resource_path    TEXT;
ALTER TABLE public.api_request_log_for_migration ADD COLUMN IF NOT EXISTS request_headers  TEXT;
ALTER TABLE public.api_request_log_for_migration ADD COLUMN IF NOT EXISTS response_headers TEXT;
ALTER TABLE public.api_request_log_for_migration ADD COLUMN IF NOT EXISTS request_format   VARCHAR(10);
ALTER TABLE public.api_request_log_for_migration ADD COLUMN IF NOT EXISTS response_format  VARCHAR(10);
ALTER TABLE public.api_request_log_for_migration ADD COLUMN IF NOT EXISTS response_content_type VARCHAR(255);

CREATE INDEX IF NOT EXISTS idx_api_request_log_api_name
    ON public.api_request_log_for_migration (api_name, request_time);
