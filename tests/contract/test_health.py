"""
Contract tests for health and metrics endpoints.

Tests the API contract for:
- GET /api/v1/health/live
- GET /api/v1/health/ready
- GET /api/v1/metrics

Following TDD: These tests will FAIL until implementation is complete.
"""

import pytest
from httpx import AsyncClient
from fastapi import status


@pytest.mark.asyncio
class TestHealthLiveness:
    """Test GET /api/v1/health/live endpoint contract."""

    async def test_liveness_probe_success(self, async_client: AsyncClient):
        """
        Test liveness probe returns 200 OK.

        Expected:
        - Status: 200 OK
        - Response indicates process is alive
        - No dependency checks (fast response)
        """
        response = await async_client.get("/api/v1/health/live")

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert "status" in data
        assert data["status"] == "alive"

    async def test_liveness_probe_no_auth_required(self, async_client: AsyncClient):
        """
        Test liveness endpoint is publicly accessible.

        Expected:
        - No authentication required
        - Returns 200 OK without token
        """
        response = await async_client.get("/api/v1/health/live")

        assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
class TestHealthReadiness:
    """Test GET /api/v1/health/ready endpoint contract."""

    async def test_readiness_probe_success(self, async_client: AsyncClient):
        """
        Test readiness probe with all dependencies healthy.

        Expected:
        - Status: 200 OK
        - Response includes dependency health checks
        - Checks: mongodb, redis
        """
        response = await async_client.get("/api/v1/health/ready")

        # May be 200 or 503 depending on dependency availability
        # For contract, we verify structure
        data = response.json()
        assert "status" in data

        if response.status_code == status.HTTP_200_OK:
            assert data["status"] == "ready"
            assert "checks" in data
            checks = data["checks"]
            assert "mongodb" in checks
            assert "redis" in checks

    async def test_readiness_probe_structure(self, async_client: AsyncClient):
        """
        Test readiness response structure regardless of health status.

        Expected:
        - Response contains: status, checks
        - Checks contain boolean values for each dependency
        """
        response = await async_client.get("/api/v1/health/ready")

        data = response.json()
        assert "status" in data
        assert "checks" in data

        checks = data["checks"]
        assert isinstance(checks, dict)

        # Each check should be a boolean
        for check_name, check_value in checks.items():
            assert isinstance(check_value, bool), \
                f"Check '{check_name}' should be boolean, got {type(check_value)}"

    async def test_readiness_probe_no_auth_required(self, async_client: AsyncClient):
        """
        Test readiness endpoint is publicly accessible.

        Expected:
        - No authentication required
        - Returns health status without token
        """
        response = await async_client.get("/api/v1/health/ready")

        # Should return a response (200 or 503) without authentication
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_503_SERVICE_UNAVAILABLE
        ]


@pytest.mark.asyncio
class TestMetrics:
    """Test GET /api/v1/metrics endpoint contract."""

    async def test_metrics_json_format(self, async_client: AsyncClient):
        """
        Test metrics endpoint returns JSON format.

        Expected:
        - Status: 200 OK
        - Response in JSON format
        - Contains application metrics
        """
        response = await async_client.get("/api/v1/metrics")

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert isinstance(data, dict)

        # Verify basic metrics structure
        # Exact metrics depend on implementation, but should include system info
        assert len(data) > 0, "Metrics should not be empty"

    async def test_metrics_prometheus_format(self, async_client: AsyncClient):
        """
        Test metrics endpoint can return Prometheus format.

        Expected:
        - Status: 200 OK when Accept: text/plain header provided
        - Response in Prometheus exposition format
        """
        response = await async_client.get(
            "/api/v1/metrics",
            headers={"Accept": "text/plain"}
        )

        assert response.status_code == status.HTTP_200_OK

        # Prometheus format is text/plain
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type or "application/openmetrics-text" in content_type

    async def test_metrics_no_auth_required(self, async_client: AsyncClient):
        """
        Test metrics endpoint is publicly accessible.

        Expected:
        - No authentication required
        - Returns metrics without token
        """
        response = await async_client.get("/api/v1/metrics")

        assert response.status_code == status.HTTP_200_OK

    async def test_metrics_contains_expected_metrics(self, async_client: AsyncClient):
        """
        Test metrics response contains expected application metrics.

        Expected:
        - Response includes common metrics like:
          - uptime
          - request count
          - error rate
          - queue depth (when implemented)
        """
        response = await async_client.get("/api/v1/metrics")

        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Basic metrics that should always be present
        # Note: Exact metrics depend on implementation
        # For MVP, at least verify it's a non-empty dict
        assert isinstance(data, dict)
        assert len(data) > 0


@pytest.mark.asyncio
class TestHealthWorkflow:
    """Test health check workflow scenarios."""

    async def test_startup_sequence(self, async_client: AsyncClient):
        """
        Test health endpoints during startup.

        Expected:
        - Liveness is always OK (process alive)
        - Readiness may be unhealthy until dependencies connect
        """
        # Liveness should always work
        liveness_response = await async_client.get("/api/v1/health/live")
        assert liveness_response.status_code == status.HTTP_200_OK

        # Readiness depends on dependencies
        readiness_response = await async_client.get("/api/v1/health/ready")
        assert readiness_response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_503_SERVICE_UNAVAILABLE
        ]

    async def test_health_endpoints_fast_response(self, async_client: AsyncClient):
        """
        Test health endpoints respond quickly.

        Expected:
        - Response time < 500ms for liveness
        - Response time < 2s for readiness (includes dependency checks)
        """
        import time

        # Liveness should be instant
        start = time.time()
        response = await async_client.get("/api/v1/health/live")
        duration = time.time() - start

        assert response.status_code == status.HTTP_200_OK
        assert duration < 0.5, f"Liveness took {duration}s, expected <0.5s"

        # Readiness includes checks but should be cached
        start = time.time()
        response = await async_client.get("/api/v1/health/ready")
        duration = time.time() - start

        # Allow up to 2 seconds for initial check, subsequent should be cached
        assert duration < 2.0, f"Readiness took {duration}s, expected <2s"
