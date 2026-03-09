"""Tests for Episode query API — Task 4.1."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import TEST_PROJECT_ID, TEST_USER_ID, make_episode, make_topic


class TestListEpisodes:
    def test_list_episodes_no_filters(self, client, auth_headers, mock_db):
        ep1 = make_episode(status="ready", quality=0.9)
        ep2 = make_episode(status="ready", quality=0.7)

        # Mock scalar result for count and scalars for items
        count_result = MagicMock()
        count_result.scalar_one.return_value = 2
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [ep1, ep2]

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = client.get("/api/v1/episodes", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    def test_list_episodes_with_status_filter(self, client, auth_headers, mock_db):
        ep = make_episode(status="ready")

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [ep]

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = client.get("/api/v1/episodes?status=ready", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert all(e["status"] == "ready" for e in data["items"])

    def test_list_episodes_with_quality_filter(self, client, auth_headers, mock_db):
        ep = make_episode(quality=0.85)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [ep]

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = client.get("/api/v1/episodes?min_quality=0.6", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(e["quality_score"] >= 0.6 for e in data["items"])

    def test_list_episodes_with_format_filter(self, client, auth_headers, mock_db):
        ep = make_episode(fmt="mcap")

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [ep]

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = client.get("/api/v1/episodes?format=mcap", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert all(e["format"] == "mcap" for e in data["items"])

    def test_list_episodes_combined_filters(self, client, auth_headers, mock_db):
        ep = make_episode(status="ready", fmt="mcap", quality=0.8)

        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [ep]

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = client.get(
            "/api/v1/episodes?status=ready&format=mcap&min_quality=0.6",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_list_episodes_pagination(self, client, auth_headers, mock_db):
        count_result = MagicMock()
        count_result.scalar_one.return_value = 100
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [make_episode() for _ in range(20)]

        mock_db.execute = AsyncMock(side_effect=[count_result, items_result])

        resp = client.get("/api/v1/episodes?limit=20&offset=40", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 100
        assert len(data["items"]) == 20

    def test_list_episodes_unauthenticated(self, client):
        resp = client.get("/api/v1/episodes")
        assert resp.status_code in (401, 403)  # HTTPBearer returns 401/403 when no token


class TestGetEpisodeDetail:
    def test_get_episode_detail_success(self, client, auth_headers, mock_db):
        ep = make_episode()
        topic = make_topic(ep)
        ep.topics = [topic]

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep

        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(f"/api/v1/episodes/{ep.id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(ep.id)
        assert "topics" in body
        assert len(body["topics"]) == 1
        assert body["topics"][0]["name"] == "/camera/image_raw"

    def test_get_episode_detail_not_found(self, client, auth_headers, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(f"/api/v1/episodes/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    def test_get_episode_wrong_project(self, client, auth_headers, mock_db):
        """Episode belonging to different project returns 404."""
        ep = make_episode(project_id=str(uuid.uuid4()))  # different project

        result = MagicMock()
        result.scalar_one_or_none.return_value = None  # filtered out by project_id
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(f"/api/v1/episodes/{ep.id}", headers=auth_headers)
        assert resp.status_code == 404


class TestStreamToken:
    def test_get_stream_token(self, client, auth_headers, mock_db):
        ep = make_episode()

        result = MagicMock()
        result.scalar_one_or_none.return_value = ep
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(f"/api/v1/episodes/{ep.id}/stream-token", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "stream_token" in body
        assert body["expires_in"] == 3600

    def test_stream_token_episode_not_found(self, client, auth_headers, mock_db):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result)

        resp = client.get(f"/api/v1/episodes/{uuid.uuid4()}/stream-token", headers=auth_headers)
        assert resp.status_code == 404
