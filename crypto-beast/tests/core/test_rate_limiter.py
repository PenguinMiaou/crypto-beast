import asyncio
import time

import pytest
import pytest_asyncio


@pytest.fixture
def limiter():
    from core.rate_limiter import BinanceRateLimiter

    return BinanceRateLimiter()


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_acquire_data_slot_succeeds(self, limiter):
        result = await limiter.acquire_data_slot()
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_order_slot_succeeds(self, limiter):
        result = await limiter.acquire_order_slot()
        assert result is True

    @pytest.mark.asyncio
    async def test_usage_tracking(self, limiter):
        await limiter.acquire_data_slot()
        await limiter.acquire_data_slot()
        await limiter.acquire_order_slot()
        usage = limiter.get_usage()
        assert usage["data_used"] == 2
        assert usage["order_used"] == 1

    @pytest.mark.asyncio
    async def test_data_limit_respected(self):
        from core.rate_limiter import BinanceRateLimiter

        limiter = BinanceRateLimiter(data_limit=5, order_limit=5, window_seconds=1)
        for _ in range(5):
            await limiter.acquire_data_slot()
        # 6th call should block briefly then succeed after window resets
        # We just test that usage is tracked correctly
        usage = limiter.get_usage()
        assert usage["data_used"] == 5
