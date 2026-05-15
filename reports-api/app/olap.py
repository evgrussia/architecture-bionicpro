"""Доступ к OLAP-витрине ClickHouse."""
from __future__ import annotations

from datetime import date
from typing import Optional

from clickhouse_driver import Client


class OlapRepository:
    def __init__(self, host: str, port: int, database: str, user: str = "default", password: str = "") -> None:
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password

    def _client(self) -> Client:
        return Client(
            host=self._host,
            port=self._port,
            database=self._database,
            user=self._user,
            password=self._password,
        )

    def get_watermark(self) -> Optional[date]:
        rows = self._client().execute(
            """
            SELECT max(watermark)
            FROM reports.etl_watermark FINAL
            WHERE pipeline = %(p)s
            """,
            {"p": "user_daily_mart"},
        )
        if rows and rows[0][0]:
            return rows[0][0]
        return None

    def fetch_user_report(self, user_id: str, date_from: date, date_to: date) -> list[dict]:
        rows = self._client().execute(
            """
            SELECT
                day,
                country,
                prosthetic_model,
                steps_total,
                motor_load_avg,
                battery_min,
                errors_count
            FROM reports.user_daily_mart FINAL
            WHERE user_id = %(u)s
              AND day BETWEEN %(d_from)s AND %(d_to)s
            ORDER BY day
            """,
            {"u": user_id, "d_from": date_from, "d_to": date_to},
        )
        return [
            {
                "day": str(r[0]),
                "country": r[1],
                "prosthetic_model": r[2],
                "steps_total": int(r[3]),
                "motor_load_avg": float(r[4]),
                "battery_min": float(r[5]),
                "errors_count": int(r[6]),
            }
            for r in rows
        ]
