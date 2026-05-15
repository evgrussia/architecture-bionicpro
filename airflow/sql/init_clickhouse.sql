-- OLAP-схема для сервиса отчётов BionicPRO.
-- ORDER BY (user_id, day) даёт быстрые точечные чтения по пользователю и периоду.

CREATE DATABASE IF NOT EXISTS reports;

CREATE TABLE IF NOT EXISTS reports.user_daily_mart
(
    user_id        String,
    day            Date,
    country        LowCardinality(String),
    prosthetic_model LowCardinality(String),
    steps_total    UInt64,
    motor_load_avg Float64,
    battery_min    Float64,
    errors_count   UInt32,
    updated_at     DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
PARTITION BY toYYYYMM(day)
ORDER BY (user_id, day);

-- Watermark: до какой даты витрина считается полной.
-- API не отдаёт периоды за пределами watermark.
CREATE TABLE IF NOT EXISTS reports.etl_watermark
(
    pipeline   String,
    watermark  Date,
    updated_at DateTime DEFAULT now()
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY pipeline;
