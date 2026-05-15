# Задание 2. Сервис отчётов BionicPRO

## Архитектура (C4)

Файл: [`c4-reports.drawio`](./c4-reports.drawio).

Поток данных:

```
CRM (Postgres) ─┐
                ├──► Airflow DAG etl_reports_dag (hourly) ─► ClickHouse: reports.user_daily_mart
Telemetry (PG) ─┘                                           reports.etl_watermark
                                                                       ▲
                                                            Reports API (FastAPI)
                                                                       ▲
                                                        Frontend (Keycloak + PKCE)
```

## Задача 2. Airflow DAG

`airflow/dags/etl_reports_dag.py` — DAG `etl_reports_dag`, `schedule_interval=@hourly`.

Логика:
1. Читает текущий watermark из `reports.etl_watermark`.
2. Перебирает **только закрытые** дни (`day < today`) с момента предыдущего watermark.
3. Извлекает агрегаты по `(user_id, day)` из `telemetry_events` (Postgres).
4. Подмешивает справочные поля из `crm_clients` (страна, модель).
5. Льёт в `reports.user_daily_mart` (ClickHouse ReplacingMergeTree, `ORDER BY (user_id, day)`).
6. Двигает watermark.

Витрина денормализована и упорядочена по `(user_id, day)` — выборка отчёта пользователя сводится к одному range-скану без join'ов.

## Задача 3. Backend `/reports`

`reports-api/` — FastAPI.

`GET /reports?from=YYYY-MM-DD&to=YYYY-MM-DD`:
- требует `Authorization: Bearer <JWT>`;
- валидирует JWT по JWKS Keycloak (`iss`, `aud=reports-api`, `exp`, подпись RS256);
- идентификатор пользователя берётся **из `sub`** токена, не из query;
- читает только из OLAP, без вычислений в рантайме.

## Задача 4. Ограничение доступа

- Нет JWT или JWT невалиден → `401`.
- Параметр `user_id` в query, не совпадающий с `sub` из токена → `403`.
- В SQL-запрос подставляется **только** `sub`. Чужие данные физически недостижимы.
- Period clamping: `effective_to = min(date_to, watermark)`. Если запрошенный период за пределами watermark, API возвращает пустой результат + `warning`, но **не** трогает «горячие» дни, которые ещё не обработал Airflow.

## Задача 5. UI

`frontend/src/components/ReportPage.tsx`:
- кнопка «Get Report» вызывает `GET /reports` с `Authorization: Bearer ${keycloak.token}`;
- перед запросом `keycloak.updateToken(30)` — освежение access-токена;
- ответ рендерится как сводка (дни/шаги/ошибки) и таблица по дням;
- если сервер вернул `warning` (период за watermark) — выводится жёлтый бэйдж.

## Чек-лист требований задания

| Требование | Где закрыто |
|---|---|
| UI вызывает API для генерации отчёта | `frontend/src/components/ReportPage.tsx` — `downloadReport()` |
| Неаутентифицированный не может сгенерировать отчёт | `reports-api/app/main.py` — `Depends(current_user)` → 401; UI скрывает экран до `keycloak.authenticated` |
| Пользователь видит только свой отчёт | `reports-api/app/main.py` — `sub` из токена, query `user_id != sub` → 403 |
| OLAP-источник | `reports-api/app/olap.py` — ClickHouse `reports.user_daily_mart` |
| Период не выходит за обработанное Airflow | `reports-api/app/main.py` — clamp по `etl_watermark`; DAG двигает watermark только после успешной загрузки |

## Запуск

```bash
docker compose up --build
# Keycloak    http://localhost:8080  (admin/admin)
# Airflow UI  http://localhost:8081  (admin/admin)
# Reports API http://localhost:8000/docs
# Frontend    http://localhost:3000
```

В Airflow UI включить DAG `etl_reports_dag` (или дождаться его запуска по расписанию).
