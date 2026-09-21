import os

import pytest

from src.providers.model_factory import create_model_from_env

_SAVED_KEYS = ["LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"]


@pytest.fixture(autouse=True)
def _restore_env():
    saved = {key: os.environ.get(key) for key in _SAVED_KEYS}
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_maps_llm_api_key_to_gemini_api_key_for_google_provider():
    os.environ["LLM_PROVIDER"] = "google"
    os.environ["LLM_MODEL"] = "gemini-test"
    os.environ["LLM_API_KEY"] = "test-google-key"
    os.environ.pop("GOOGLE_API_KEY", None)
    os.environ.pop("GEMINI_API_KEY", None)

    create_model_from_env()

    assert "GOOGLE_API_KEY" not in os.environ
    assert os.environ["GEMINI_API_KEY"] == "test-google-key"


def test_raises_for_unsupported_provider():
    os.environ["LLM_PROVIDER"] = "does-not-exist"
    os.environ["LLM_MODEL"] = "some-model"
    os.environ.pop("LLM_API_KEY", None)

    with pytest.raises(RuntimeError, match="未対応のプロバイダー"):
        create_model_from_env()
