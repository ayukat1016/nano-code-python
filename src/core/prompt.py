"""システムプロンプト（指示文）の読み込み。"""
from __future__ import annotations

from pathlib import Path


def load_instructions(workspace_root: str) -> str:
    # ベースプロンプトを読み込む（必須）
    base_path = Path(__file__).resolve().parent / "prompt.md"
    base = base_path.read_text(encoding="utf-8")

    # AGENTS.md を読み込む（任意）
    agents_md_path = Path(workspace_root) / "AGENTS.md"
    if agents_md_path.exists():
        agents_md = agents_md_path.read_text(encoding="utf-8")
        return f"{base}\n\n# プロジェクト固有の指示\n\n{agents_md}"

    return base
