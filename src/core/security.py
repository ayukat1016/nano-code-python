"""ファイルパスやコマンド文字列に対する軽量なセキュリティチェック。"""
from __future__ import annotations

import os
import re
from typing import Optional

# 機密ファイルのパターン
SENSITIVE_FILE_PATTERNS = [
    re.compile(r"\.env$"),
    re.compile(r"\.env\."),
    re.compile(r"credentials\.json$"),
    re.compile(r"\.ssh/id_rsa$"),
    re.compile(r"\.pgpass$"),
    re.compile(r"\.kube/config$"),
    re.compile(r"\.aws/credentials$"),
]


def is_sensitive_file(file_path: str) -> bool:
    normalized = os.path.normpath(file_path)
    return any(pattern.search(normalized) for pattern in SENSITIVE_FILE_PATTERNS)


# 危険なコマンドパターン
DANGEROUS_PATTERNS = [
    re.compile(r"[^\\]>"),  # リダイレクト（>、>>）
    re.compile(r"\$\("),  # コマンド置換 $()
    re.compile(r"`"),  # バッククォート置換
    re.compile(r"\beval\b"),  # eval
    re.compile(r"\$\{[^}]*##"),  # 変数難読化
]


def is_dangerous_command(command: str) -> tuple[bool, Optional[str]]:
    if re.search(r"\bsudo\b", command):
        return True, "sudo による権限昇格は禁止されています"
    if any(pattern.search(command) for pattern in DANGEROUS_PATTERNS):
        return True, "危険なパターンが検出されました"
    return False, None


ALLOWED_ENV_VARS = ["PATH", "HOME", "USER", "LANG", "PYTHON_ENV"]


def filter_env(env: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in env.items() if key in ALLOWED_ENV_VARS}
