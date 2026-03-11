"""E2E tests — Authentication API.

Covers: register, login, token validation, duplicate user, invalid credentials.
"""
from __future__ import annotations

import uuid

import httpx
import pytest

from .conftest import GATEWAY_URL, E2E_PROJECT_ID
from .helpers import E2EClient


@pytest.mark.e2e
class TestRegister:
    async def test_register_success(self) -> None:
        unique = uuid.uuid4().hex[:8]
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
            resp = await client.post(
                "/auth/register",
                json={
                    "email": f"reg_{unique}@test.local",
                    "password": "password123",
                    "name": f"User {unique}",
                    "role": "annotator_internal",
                    "project_id": E2E_PROJECT_ID,
                },
            )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "id" in body or "user" in body, f"Response missing user info: {body}"

    async def test_register_duplicate_email(self) -> None:
        unique = uuid.uuid4().hex[:8]
        email = f"dup_{unique}@test.local"
        payload = {
            "email": email,
            "password": "password123",
            "name": "Dup User",
            "role": "annotator_internal",
            "project_id": E2E_PROJECT_ID,
        }
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
            r1 = await client.post("/auth/register", json=payload)
            assert r1.status_code == 201, f"First register failed: {r1.text}"
            r2 = await client.post("/auth/register", json=payload)
        assert r2.status_code in (409, 422, 400), (
            f"Duplicate register should fail, got {r2.status_code}: {r2.text}"
        )

    async def test_register_invalid_email(self) -> None:
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
            resp = await client.post(
                "/auth/register",
                json={
                    "email": "not-an-email",
                    "password": "password123",
                    "name": "Bad User",
                    "role": "annotator_internal",
                    "project_id": E2E_PROJECT_ID,
                },
            )
        assert resp.status_code in (400, 422), f"Expected 400 or 422, got {resp.status_code}: {resp.text}"

    async def test_register_missing_fields(self) -> None:
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
            resp = await client.post("/auth/register", json={"email": "x@x.com"})
        assert resp.status_code in (400, 422), f"Expected 400 or 422, got {resp.status_code}: {resp.text}"


@pytest.mark.e2e
class TestLogin:
    async def test_login_success(self) -> None:
        unique = uuid.uuid4().hex[:8]
        email = f"login_{unique}@test.local"
        password = "secure_pass_456"
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
            await client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "name": "Login User",
                    "role": "annotator_internal",
                    "project_id": E2E_PROJECT_ID,
                },
            )
            resp = await client.post("/auth/login", json={"email": email, "password": password})

        assert resp.status_code == 200, f"Login failed: {resp.text}"
        body = resp.json()
        assert "token" in body, f"Response missing 'token': {body}"
        assert "user" in body, f"Response missing 'user': {body}"
        assert body["user"]["email"] == email

    async def test_login_wrong_password(self) -> None:
        unique = uuid.uuid4().hex[:8]
        email = f"wrongpw_{unique}@test.local"
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
            await client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": "correct_pw",
                    "name": "Pw User",
                    "role": "annotator_internal",
                    "project_id": E2E_PROJECT_ID,
                },
            )
            resp = await client.post(
                "/auth/login", json={"email": email, "password": "wrong_pw"}
            )
        assert resp.status_code in (401, 403), (
            f"Wrong password should return 401/403, got {resp.status_code}: {resp.text}"
        )

    async def test_login_nonexistent_user(self) -> None:
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
            resp = await client.post(
                "/auth/login",
                json={"email": "nobody@nowhere.invalid", "password": "any"},
            )
        assert resp.status_code in (401, 404), (
            f"Nonexistent user should return 401/404, got {resp.status_code}: {resp.text}"
        )

    async def test_unauthenticated_request_rejected(self) -> None:
        async with httpx.AsyncClient(base_url=GATEWAY_URL, timeout=15.0) as client:
            resp = await client.get("/api/v1/episodes")
        assert resp.status_code == 401, (
            f"Unauthenticated request should return 401, got {resp.status_code}: {resp.text}"
        )

    async def test_invalid_token_rejected(self) -> None:
        async with httpx.AsyncClient(
            base_url=GATEWAY_URL,
            headers={"Authorization": "Bearer invalid.token.here"},
            timeout=15.0,
        ) as client:
            resp = await client.get("/api/v1/episodes")
        assert resp.status_code == 401, (
            f"Invalid token should return 401, got {resp.status_code}: {resp.text}"
        )
