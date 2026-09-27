"""環境変数からLangChainのChatModelを組み立てるファクトリ。

src/providers/model_factory.py の LangChain版。プロバイダーごとに別々の
Provider実装（anthropic_provider.py等）を自前で書く必要がなく、
langchain-openai / langchain-anthropic / langchain-google-genai の
統一インタフェース（BaseChatModel）に差し替わるだけになる。
"""
from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel


def create_model_from_env() -> BaseChatModel:
    provider = os.environ.get("LLM_PROVIDER")
    model_name = os.environ.get("LLM_MODEL")
    api_key = os.environ.get("LLM_API_KEY")

    if not provider:
        raise RuntimeError("LLM_PROVIDER 環境変数が設定されていません")
    if not model_name:
        raise RuntimeError("LLM_MODEL 環境変数が設定されていません")

    provider_lower = provider.lower()

    # LLM_API_KEY はCI(GitHub Actions Secrets)向けの共通変数。
    # ローカルの.envのようにプロバイダー固有の環境変数（OPENAI_API_KEY等）が
    # 既に設定されている場合はそちらを優先する（src/providers/model_factory.py と同じ方針）。
    if provider_lower == "openai":
        from langchain_openai import ChatOpenAI

        if api_key and not os.environ.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = api_key
        return ChatOpenAI(model=model_name)

    if provider_lower == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if api_key and not os.environ.get("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = api_key
        return ChatAnthropic(model=model_name)

    if provider_lower == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if api_key and not os.environ.get("GOOGLE_API_KEY"):
            os.environ["GOOGLE_API_KEY"] = api_key
        return ChatGoogleGenerativeAI(model=model_name)

    raise RuntimeError(f"未対応のプロバイダー: {provider}. 対応プロバイダー: openai, anthropic, google")
