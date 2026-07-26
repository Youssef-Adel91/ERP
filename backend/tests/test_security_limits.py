from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_payload_size_limit():
    # Make a request with a Content-Length > 5MB
    large_payload = b"0" * (5 * 1024 * 1024 + 10)
    
    # We use a custom transport to avoid the test client automatically recalculating content-length
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Verify large payload is rejected
        response = await client.post(
            "/health", 
            content=large_payload,
            headers={"Content-Length": str(len(large_payload))},
        )
        assert response.status_code == 413
        assert response.json()["detail"] == "Payload Too Large"
        
        # 2. Verify whitelisted endpoint accepts large payload
        # It will likely return 404 or 405 because the endpoint doesn't exist yet, 
        # but it shouldn't return 413.
        response = await client.post(
            "/api/v1/attachments/upload", 
            content=large_payload,
            headers={"Content-Length": str(len(large_payload))},
        )
        assert response.status_code != 413


@pytest.mark.asyncio
async def test_rate_limiter_blocks_after_300_requests():
    # Mock Redis so we don't need a real Redis instance for this test
    mock_redis = MagicMock()
    mock_pipeline = MagicMock() # Use MagicMock so incr/expire are sync
    
    # We will simulate the pipeline returning incrementing counts
    counts = iter([i, True] for i in range(1, 400))
    
    async def mock_execute():
        return next(counts)

    mock_pipeline.execute = mock_execute
    
    # __aenter__ must be async and return the pipeline
    async def mock_aenter(self):
        return mock_pipeline
        
    async def mock_aexit(self, *args):
        pass

    mock_pipeline_cm = MagicMock()
    mock_pipeline_cm.__aenter__ = mock_aenter
    mock_pipeline_cm.__aexit__ = mock_aexit
    mock_redis.pipeline.return_value = mock_pipeline_cm
    
    # Patch the redis_client imported in throttling.py
    with patch("app.core.security.throttling.redis_client", mock_redis):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Fire 300 requests, they should all be 200 OK (health endpoint)
            for i in range(300):
                res = await client.get("/health")
                assert res.status_code == 200, f"Request {i+1} failed"
                
            # The 301st request should be blocked
            res = await client.get("/health")
            assert res.status_code == 429
            assert res.json()["detail"] == "Too Many Requests"
            assert "Retry-After" in res.headers
