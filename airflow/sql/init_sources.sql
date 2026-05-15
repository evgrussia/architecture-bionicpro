-- Демонстрационные источники: CRM и телеметрия (Postgres).
--
-- Этот файл подключён как docker-entrypoint к двум контейнерам:
--   * crm_db        — здесь содержательная только таблица crm_clients;
--   * telemetry_db  — здесь содержательная только таблица telemetry_events.
-- Скрипт идемпотентен (ON CONFLICT / WHERE NOT EXISTS), общая структура одна.
--
-- user_id в обеих таблицах = Keycloak username (preferred_username),
-- т.к. именно по нему API сопоставляет владельца отчёта.

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

-- CRM: реальные пользователи Keycloak (см. keycloak/realm-export.json).
-- prothetic_user сохранён ради обратной совместимости.
INSERT INTO crm_clients (user_id, full_name, country, prosthetic_model, contract_started) VALUES
    ('prothetic1',     'Prothetic One',   'RU', 'BionicArm-X1', '2025-01-15'),
    ('prothetic2',     'Prothetic Two',   'RU', 'BionicLeg-L2', '2025-02-10'),
    ('prothetic3',     'Prothetic Three', 'DE', 'BionicArm-X2', '2025-03-05'),
    ('prothetic_user', 'Иван Иванов',     'RU', 'BionicArm-X1', '2025-01-15'),
    ('user-de-001',    'Hans Müller',     'DE', 'BionicLeg-L2', '2025-03-01')
ON CONFLICT (user_id) DO NOTHING;

-- Телеметрия: 30 закрытых дней × 6 точек/сутки × 3 пользователя.
-- Покрываем именно вчерашний день и старее (DAG не трогает «открытый» сегодня).
-- Защита от повторного запуска: вставляем только если таблица пуста.
INSERT INTO telemetry_events (user_id, event_time, steps, motor_load, battery, is_error)
SELECT
    u.user_id,
    ((CURRENT_DATE - d.offset_days)::timestamp + (h.hour_of_day || ' hour')::interval)
        AT TIME ZONE 'UTC' AS event_time,
    (200 + (random() * 1500)::int)                 AS steps,
    round((0.2 + random() * 0.6)::numeric, 3)::float8 AS motor_load,
    round((40 + random() * 60)::numeric, 1)::float8   AS battery,
    (random() < 0.04)                              AS is_error
FROM (VALUES ('prothetic1'), ('prothetic2'), ('prothetic3')) AS u(user_id)
CROSS JOIN generate_series(1, 30) AS d(offset_days)
CROSS JOIN generate_series(0, 23, 4) AS h(hour_of_day)
WHERE NOT EXISTS (SELECT 1 FROM telemetry_events LIMIT 1);
