# セキュアで最小限のPython開発環境
# 非rootユーザー / 権限制限 / プロジェクトディレクトリのみ
FROM python:3.12-slim

# 必須ツールのみ（git, jq, curl, nano, bubblewrap）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    jq \
    curl \
    ca-certificates \
    nano \
    bubblewrap \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# 非rootユーザーを作成
RUN useradd -ms /bin/bash vscode
USER vscode

# 基本環境変数（nanoはテキストエディタ、プロジェクト名とは無関係）
ENV EDITOR=nano
ENV DEVCONTAINER=true

# pip install --user のインストール先をPATHに追加（venvを使わず直接インストールするため）
ENV PATH="/home/vscode/.local/bin:$PATH"

CMD ["bash"]
