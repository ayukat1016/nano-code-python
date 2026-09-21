"""許可リストにあるドメインのみ取得できる Web 取得ツール。"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import config
from ..types import Tool


async def web_fetch_execute(args: dict[str, Any]) -> str:
    url = args["url"]

    # URLのパース（バリデーション含む）
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("無効なURL形式です")

    hostname = parsed.hostname

    # ガードレール: 許可リストのチェック
    is_allowed = any(
        hostname == domain or hostname.endswith(f".{domain}") for domain in config.allowed_domains
    )

    if not is_allowed:
        raise ValueError(
            f"セキュリティエラー: ドメイン '{hostname}' へのアクセスは許可されていません。\n"
            f"許可リスト: {', '.join(config.allowed_domains)}"
        )

    # 実際のフェッチ処理（リダイレクトは許可リスト回避に使われうるため追従しない）
    async with httpx.AsyncClient(follow_redirects=False) as client:
        response = await client.get(url)

    if not (200 <= response.status_code < 300):
        raise RuntimeError(f"HTTP Error: {response.status_code} {response.reason_phrase}")

    return response.text


web_fetch = Tool(
    name="webFetch",
    description="指定されたURLのWebページを取得します",
    needs_approval=True,
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "取得したいURL"},
        },
        "required": ["url"],
    },
    execute=web_fetch_execute,
)
