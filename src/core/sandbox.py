"""bubblewrap (bwrap) を使ったプロセス隔離サンドボックス。"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class SandboxOptions:
    cwd: Optional[str] = None  # 作業ディレクトリ
    allow_network: bool = False  # ネットワークアクセスの許可
    env: Optional[dict[str, str]] = None  # 環境変数


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int


class Sandbox:
    async def run(
        self,
        command: str,
        args: list[str],
        options: Optional[SandboxOptions] = None,
    ) -> SandboxResult:
        options = options or SandboxOptions()
        cwd = options.cwd or os.getcwd()

        # bwrap の引数を構築
        bwrap_args: list[str] = [
            # 1. ファイルシステムの隔離
            # ルートを読み取り専用でバインド（システム破壊の防止）
            "--ro-bind", "/", "/",
            # デバイスファイルと一時ディレクトリを新規作成
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            # 作業ディレクトリのみ書き込み許可でバインド
            "--bind", cwd, cwd,
            "--chdir", cwd,
            # 親プロセス(Python)が終了したらサンドボックスも終了（ゾンビ防止）
            "--die-with-parent",
            # 環境変数をクリア
            "--clearenv",
        ]

        # 環境変数の再設定（PATH などを引き継ぐ）
        env_vars = {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": "/tmp",
            **(options.env or {}),
        }
        for key, value in env_vars.items():
            if value is not None:
                bwrap_args += ["--setenv", key, value]

        # 2. ネットワーク制御
        if not options.allow_network:
            bwrap_args.append("--unshare-net")  # ネットワーク名前空間を分離（通信遮断）

        # 実行するコマンド
        bwrap_args += ["--", command, *args]

        # プロセス生成と結果取得
        try:
            proc = await asyncio.create_subprocess_exec(
                "bwrap",
                *bwrap_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            return SandboxResult(
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
                exit_code=proc.returncode if proc.returncode is not None else -1,
            )
        except FileNotFoundError as err:
            # bwrap 自体の起動失敗をハンドリング
            return SandboxResult(
                stdout="",
                stderr=(
                    f"Sandbox Error: {err}\n"
                    "(Hint: docker run の --cap-add=SYS_ADMIN オプションを確認してください)"
                ),
                exit_code=126,
            )
