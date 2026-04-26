from __future__ import annotations

import os

import pytest


@pytest.mark.integration_live
def test_live_env_has_exa_api_key():
    api_key = os.getenv("EXA_API_KEY")
    if not api_key:
        pytest.skip("EXA_API_KEY is not set in environment")
    assert len(api_key) > 10
