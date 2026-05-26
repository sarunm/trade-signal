import os

import pytest


@pytest.mark.asyncio
async def test_adaptive_tuner_function_imports():
    os.environ["ADAPTIVE_ENABLED"] = "1"
    from main import _safe_run_adaptive_tuner
    assert callable(_safe_run_adaptive_tuner)
