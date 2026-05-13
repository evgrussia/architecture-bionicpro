"""ETL для сервиса отчётов BionicPRO.

Источники:
  - CRM (PostgreSQL): профили пользователей.
  - Telemetry (PostgreSQL): сырые события протезов.

Назначение:
  - reports.user_daily_mart в ClickHouse — денормализованная витрина
    по (user_id, day) для быстрых выборок в Reports API.
  - reports.etl_watermark — последний полностью обработанный день,
    чтобы API не отдавал «ещё не посчитанные» периоды.

Стратегия:
  - Инкрементально обрабатываем закрытые дни (вчера и старее) с момента
    предыдущего watermark. Текущий день не трогаем — он ещё «открыт».
"""
from __future__ import annotations

from datetime import datetime, timedelta, date
import logging

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook

try:
    from airflow.providers.common.sql.hooks.sql import DbApiHook  # noqa: F401
except ImportError:
    pass

from clickhouse_driver import Client as ClickHouseClient

log = logging.getLogger(__name__)

CRM_CONN_ID = "crm_postgres"
TELEMETRY_CONN_ID = "telemetry_postgres"

CLICKHOUSE_HOST = "clickhouse"
CLICKHOUSE_PORT = 9000
CLICKHOUSE_DB = "reports"

PIPELINE_NAME = "user_daily_mart"


def _ch_client() -> ClickHouseClient:
    return ClickHouseClient(
        host=CLICKHOUSE_HOST,
        port=CLICKHOUSE_PORT,
        database=CLICKHOUSE_DB,
    )


def _read_watermark(ch: ClickHouseClient) -> date:
    rows = ch.execute(
        """
        SELECT max(watermark)
        FROM reports.etl_watermark FINAL
        WHERE pipeline = %(p)s
        """,
        {"p": PIPELINE_NAME},
    )
    if rows and rows[0][0]:
        return rows[0][0]
    return date(2025, 1, 1)


def _closed_days(start_after: date, today: date) -> list[date]:
    days: list[date] = []
    d = start_after + timedelta(days=1)
    last_closed = today - timedelta(days=1)
    while d <= last_closed:
        days.append(d)
        d += timedelta(days=1)
    return days


def extract_and_load(**context) -> None:
    ch = _ch_client()
    today = context["data_interval_end"].date()

    last_watermark = _read_watermark(ch)
    days = _closed_days(last_watermark, today)

    if not days:
        log.info("Нет новых закрытых дней для обработки. watermark=%s", last_watermark)
        return

    period_start, period_end = days[0], days[-1]
    log.info("Обработка дней [%s..%s]", period_start, period_end)

    crm_hook = PostgresHook(postgres_conn_id=CRM_CONN_ID)
    crm_rows = crm_hook.get_records(
        "SELECT user_id, country, prosthetic_model FROM crm_clients"
    )
    crm_by_user = {
        r[0]: {"country": r[1], "prosthetic_model": r[2]} for r in crm_rows
    }
    log.info("CRM: %d пользователей", len(crm_by_user))

    telemetry_hook = PostgresHook(postgres_conn_id=TELEMETRY_CONN_ID)
    telemetry_sql = """
        SELECT
            user_id,
            (event_time AT TIME ZONE 'UTC')::date AS day,
            COALESCE(SUM(steps), 0)        AS steps_total,
            COALESCE(AVG(motor_load), 0)   AS motor_load_avg,
            COALESCE(MIN(battery), 100)    AS battery_min,
            COALESCE(SUM(CASE WHEN is_error THEN 1 ELSE 0 END), 0) AS errors_count
        FROM telemetry_events
        WHERE event_time >= %s::timestamptz
          AND event_time <  (%s::date + 1)::timestamptz
        GROUP BY user_id, day
    """
    rows = telemetry_hook.get_records(telemetry_sql, parameters=(period_start, period_end))
    log.info("Telemetry: %d (user, day) групп", len(rows))

    if not rows:
        _bump_watermark(ch, period_end)
        return

    batch = []
    for user_id, day, steps_total, motor_load_avg, battery_min, errors_count in rows:
        crm = crm_by_user.get(user_id, {"country": "UNKNOWN", "prosthetic_model": "UNKNOWN"})
        batch.append((
            user_id,
            day,
            crm["country"],
            crm["prosthetic_model"],
            int(steps_total),
            float(motor_load_avg),
            float(battery_min),
            int(errors_count),
        ))

    ch.execute(
        """
        INSERT INTO reports.user_daily_mart
            (user_id, day, country, prosthetic_model,
             steps_total, motor_load_avg, battery_min, errors_count)
        VALUES
        """,
        batch,
    )
    log.info("Загружено %d строк в reports.user_daily_mart", len(batch))

    _bump_watermark(ch, period_end)


def _bump_watermark(ch: ClickHouseClient, watermark: date) -> None:
    ch.execute(
        "INSERT INTO reports.etl_watermark (pipeline, watermark) VALUES",
        [(PIPELINE_NAME, watermark)],
    )
    log.info("Watermark обновлён: %s -> %s", PIPELINE_NAME, watermark)


default_args = {
    "owner": "bionicpro-data",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="etl_reports_dag",
    description="Сборка витрины reports.user_daily_mart из CRM + telemetry",
    start_date=datetime(2025, 1, 1),
    schedule_interval="@hourly",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["bionicpro", "reports", "etl"],
) as dag:

    run_etl = PythonOperator(
        task_id="extract_transform_load",
        python_callable=extract_and_load,
    )
