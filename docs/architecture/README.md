# Задание 1. Повышение безопасности BionicPRO

## Задача 1. Архитектурное решение (C4)

Файл диаграммы: [`c4-auth.drawio`](./c4-auth.drawio) (открывается на https://app.diagrams.net).

### Требования и как они закрыты

| Требование задания | Решение в архитектуре |
|---|---|
| Унификация доступа через внешний IdP в стране представительства | Keycloak настроен как **Identity Broker**. Для каждой страны заведён отдельный Identity Provider (OIDC/SAML). Маршрутизация — через `kc_idp_hint` или Home Realm Discovery по домену email / поддомену (`ru.bionicpro.io`, `de.bionicpro.io`). |
| Не нарушать локальное хранение PII / медданных | Внешнему IdP передаётся только идентификатор пользователя. ПДн и медицинские данные хранятся в **локальной БД страны представительства** (data residency). Keycloak хранит только `sub`, `country`, роли — без медданных. Identity Provider Mapper фильтрует claims на входе. |
| Фронтенд не должен получать токены IdP | Введён **Auth BFF** (Backend-for-Frontend). Он сам проходит Authorization Code + PKCE с Keycloak, хранит access/refresh-токены в Redis. В браузер отдаётся только **HttpOnly + Secure + SameSite=Strict** session-cookie. Запросы к Reports API идут через BFF, который подставляет `Authorization: Bearer …` на сервере. Соответствует OAuth 2.0 BCP for Browser-Based Apps. |
| Поддержка нескольких IdP в разных странах | Один Keycloak с N брокерскими Identity Providers; добавление новой страны = добавление IdP в админке Keycloak без изменений во фронте, BFF, API. |

### Поток аутентификации

1. Браузер → BFF: `GET /login` (опц. `?country=de`).
2. BFF генерирует `state`, `code_verifier`, `code_challenge=S256(verifier)` и редиректит в Keycloak с `kc_idp_hint`.
3. Keycloak брокирует пользователя во внешний IdP страны (OIDC/SAML).
4. После возврата в Keycloak — выпускается локальный код, BFF меняет его на access/refresh с `code_verifier`. **Эти токены остаются в BFF/Redis.**
5. BFF ставит браузеру cookie `bp_session=<opaque>` (HttpOnly, Secure, SameSite=Strict).
6. SPA вызывает `GET /api/reports` → BFF → Reports API с `Bearer`. Reports API валидирует JWT по JWKS Keycloak и проверяет `sub == owner`.
7. Refresh выполняет BFF по таймеру; в Keycloak включён **refresh-token rotation**.

### Безопасность

- PKCE S256 обязательно для публичных клиентов.
- Direct Access Grants (ROPC) и Implicit Flow выключены.
- Access TTL — короткий; refresh — rotation + reuse detection.
- Cookie: `HttpOnly; Secure; SameSite=Strict; Path=/`; CSRF-токен в дополнение для state-changing endpoints.
- Reports API проверяет `iss`, `aud`, `exp`, `azp` и принадлежность ресурса (`sub`).

## Задача 2. Authorization Code + PKCE

Внесённые изменения:

- `frontend/src/App.tsx` — инициализация `keycloak-js` с `pkceMethod: 'S256'`. keycloak-js сам генерирует `code_verifier`/`code_challenge`, хранит verifier в `sessionStorage` и передаёт его на `/token`.
- `frontend/public/silent-check-sso.html` — стандартная страница silent SSO check (требуется при `onLoad: 'check-sso'`).
- `keycloak/realm-export.json` — клиент `reports-frontend`:
  - `attributes."pkce.code.challenge.method": "S256"` — Keycloak обязан проверять `code_verifier`,
  - `directAccessGrantsEnabled: false`, `implicitFlowEnabled: false`, `serviceAccountsEnabled: false` — публичному клиенту запрещены небезопасные гранты (OAuth 2.1).

> Примечание: в Задаче 1 предполагается дальнейшая миграция на BFF (confidential-клиент в Keycloak + HttpOnly cookie). В рамках текущего урока в код добавлен минимум — PKCE — без переписывания на BFF, чтобы оставить рабочий поток `keycloak-js`. BFF показан на C4-диаграмме как целевое состояние.
