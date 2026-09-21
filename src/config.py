"""グローバル設定。

Layer 2: プロセス隔離（bwrap によるサンドボックス）の有効/無効。
Layer 3: アプリケーション層の設定（webFetch がアクセスを許可するドメイン等）。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Config:
    sandbox: bool = False
    allowed_domains: list[str] = field(default_factory=lambda: ["api.github.com", "github.com"])


config = Config()
