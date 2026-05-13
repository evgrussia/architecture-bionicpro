"""Reports API.

Эндпоинт GET /reports — отдаёт агрегированный отчёт пользователя
из ClickHouse-витрины reports.user_daily_mart.

Гарантии:
  • без валидного JWT — 401;
  • пользователь видит только собственный отчёт (owner = sub из токена);
  • запрашиваемый период обрезается по ETL watermark, т.е. API не отдаёт
    дни, которые ещё не обработаны Airflow;
  • тяжёлых вычислений в рантайме нет — это SELECT по витрине.
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .auth import KeycloakJWTValidator
from .olap import OlapRepository

app = FastAPI(title="BionicPRO Reports API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["Authorization", "Content-Type"],
)

bearer = HTTPBearer(auto_error=False)

jwt_validator = KeycloakJWTValidator(
    issuer=os.environ["KEYCLOAK_ISSUER"],
    audience=os.getenv("KEYCLOAK_AUDIENCE", "reports-api"),
    jwks_url=os.environ["KEYCLOAK_JWKS_URL"],
)

olap = OlapRepository(
    host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
    port=int(os.getenv("CLICKHOUSE_PORT", "9000")),
    database=os.getenv("CLICKHOUSE_DB", "reports"),
    user=os.getenv("CLICKHOUSE_USER", "default"),
    password=os.getenv("CLICKHOUSE_PASSWORD", ""),
)


async def current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return await jwt_validator.validate(credentials.credentials)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/reports")
def get_report(
    user: dict = Depends(current_user),
    user_id: Optional[str] = Query(
        None,
        description="ID пользователя. Игнорируется, если не совпадает с sub из токена.",
    ),
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
) -> dict:
    sub: str = user["sub"]

    # Жёстко режем доступ: пользователь может смотреть только свой отчёт.
    if user_id is not None and user_id != sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own report",
        )

    today = date.today()
    if date_from is None:
        date_from = today - timedelta(days=30)
    if date_to is None:
        date_to = today

    if date_from > date_to:
        raise HTTPException(status_code=400, detail="`from` must be <= `to`")

    watermark = olap.get_watermark()
    if watermark is None:
        return {
            "user_id": sub,
            "period": {"from": str(date_from), "to": str(date_to)},
            "watermark": None,
            "items": [],
            "summary": _empty_summary(),
            "warning": "Витрина ещё не наполнена ETL.",
        }

    # Не отдаём периоды, которые ещё не обработал Airflow.
    effective_to = min(date_to, watermark)
    if effective_to < date_from:
        return {
            "user_id": sub,
            "period": {"from": str(date_from), "to": str(date_to)},
            "watermark": str(watermark),
            "items": [],
            "summary": _empty_summary(),
            "warning": (
                f"Запрошенный период ещё не обработан ETL (watermark={watermark})."
            ),
        }

    rows = olap.fetch_user_report(sub, date_from, effective_to)

    summary = {
        "days": len(rows),
        "steps_total": sum(r["steps_total"] for r in rows),
        "errors_count": sum(r["errors_count"] for r in rows),
    }

    return {
        "user_id": sub,
        "period": {"from": str(date_from), "to": str(effective_to)},
        "requested_to": str(date_to),
        "watermark": str(watermark),
        "items": rows,
        "summary": summary,
    }


def _empty_summary() -> dict:
    return {"days": 0, "steps_total": 0, "errors_count": 0}
