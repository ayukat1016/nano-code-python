import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 各ツールは import 時に os.getcwd() から WORKSPACE_ROOT を計算するため、
# リポジトリルートを cwd にしてから import されるようにしておく。
os.chdir(REPO_ROOT)
