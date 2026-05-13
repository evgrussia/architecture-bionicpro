"""Валидация JWT, выпущенных Keycloak.

Подтягиваем JWKS Keycloak, кэшируем ключи в памяти, проверяем подпись,
issuer, audience и exp. Возвращаем claims.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
from jose import jwt
from jose.exceptions import JWTError


class KeycloakJWTValidator:
    _JWKS_TTL_SECONDS = 600

    def __init__(self, issuer: str, audience: str, jwks_url: str) -> None:
        self.issuer = issuer
        self.audience = audience
        self.jwks_url = jwks_url
        self._jwks: dict[str, Any] | None = None
        self._jwks_loaded_at: float = 0.0
        self._lock = asyncio.Lock()

    async def _load_jwks(self) -> dict[str, Any]:
        async with self._lock:
            now = time.time()
            if self._jwks is None or (now - self._jwks_loaded_at) > self._JWKS_TTL_SECONDS:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(self.jwks_url)
                    resp.raise_for_status()
                    self._jwks = resp.json()
                    self._jwks_loaded_at = now
            assert self._jwks is not None
            return self._jwks

    async def validate(self, token: str) -> dict[str, Any]:
        jwks = await self._load_jwks()
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        key = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
        if key is None:
            # JWKS могли проротировать — перечитаем один раз.
            self._jwks = None
            jwks = await self._load_jwks()
            key = next((k for k in jwks["keys"] if k.get("kid") == kid), None)
        if key is None:
            raise JWTError(f"Unknown kid: {kid}")

        claims = jwt.decode(
            token,
            key,
            algorithms=[key.get("alg", "RS256")],
            issuer=self.issuer,
            audience=self.audience,
            options={"verify_aud": True, "verify_iss": True, "verify_exp": True},
        )
        if "sub" not in claims:
            raise JWTError("Token has no sub")
        return claims
