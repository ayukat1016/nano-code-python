"""プロバイダ実装で共有する小さなユーティリティ。

各 SDK のレスポンスは pydantic モデル（属性アクセス）だが、テストでは
プレーンな dict や SimpleNamespace で代用したいことが多いため、
辞書・オブジェクトどちらでも読み出せるアクセサを用意する。
"""
from __future__ import annotations

from typing import Any


def get_attr(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
