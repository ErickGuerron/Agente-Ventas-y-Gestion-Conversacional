import os

import pytest


@pytest.mark.live
def test_gemini_api_key_is_configured() -> None:
    # Placeholder: the real smoke call to Gemini is added with the ai_engine adapter.
    if not os.environ.get("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")
    assert os.environ["GEMINI_API_KEY"].strip()
