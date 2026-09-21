"""環境変数からプロバイダー・モデルを組み立てるファクトリ。"""
from __future__ import annotations

import os

from ..types import LanguageModel
from .anthropic_provider import create_anthropic
from .google_provider import create_google
from .openai_provider import create_openai


def create_model_from_env() -> LanguageModel:
    # 1. 環境変数を読み取る
    provider = os.environ.get("LLM_PROVIDER")
    model_name = os.environ.get("LLM_MODEL")
    api_key = os.environ.get("LLM_API_KEY")

    # 2. 必須の環境変数が未設定ならエラー
    if not provider:
        raise RuntimeError("LLM_PROVIDER 環境変数が設定されていません")
    if not model_name:
        raise RuntimeError("LLM_MODEL 環境変数が設定されていません")

    # 3. プロバイダーに応じてモデルを生成
    # LLM_API_KEY が設定されている場合、プロバイダー固有の環境変数に設定
    provider_lower = provider.lower()

    if provider_lower == "openai":
        if api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = api_key
        return create_openai()(model_name)

    if provider_lower == "anthropic":
        if api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = api_key
        return create_anthropic()(model_name)

    if provider_lower == "google":
        # google-genai SDK は GEMINI_API_KEY を自動参照するため、LLM_API_KEY もこちらへ反映する
        if api_key and not os.environ.get("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = api_key
        return create_google()(model_name)

    raise RuntimeError(f"未対応のプロバイダー: {provider}. 対応プロバイダー: openai, anthropic, google")
