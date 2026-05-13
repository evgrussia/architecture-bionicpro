-- Демонстрационные источники: CRM и телеметрия (Postgres).

CREATE TABLE IF NOT EXISTS crm_clients (
    user_id          TEXT PRIMARY KEY,
    full_name        TEXT NOT NULL,
    country          TEXT NOT NULL,
    prosthetic_model TEXT NOT NULL,
    contract_started DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS telemetry_events (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    event_time  TIMESTAMPTZ NOT NULL,
    steps       INT NOT NULL DEFAULT 0,
    motor_load  DOUBLE PRECISION NOT NULL DEFAULT 0,
    battery     DOUBLE PRECISION NOT NULL DEFAULT 100,
    is_error    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_telemetry_user_time
    ON telemetry_events (user_id, event_time);

INSERT INTO crm_clients (user_id, full_name, country, prosthetic_model, contract_started) VALUES
    ('prothetic_user', 'Иван Иванов', 'RU', 'BionicArm-X1', '2025-01-15'),
    ('user-de-001',    'Hans Müller', 'DE', 'BionicLeg-L2', '2025-03-01')
ON CONFLICT (user_id) DO NOTHING;
