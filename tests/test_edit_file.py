import os

import pytest

from src.tools.edit_file import WORKSPACE_ROOT, edit_file

TEST_FILE_NAME = "test-edit-file.txt"
TEST_FILE_PATH = os.path.join(WORKSPACE_ROOT, TEST_FILE_NAME)
INITIAL_CONTENT = "line 1: AAA\nline 2: BBB\nline 3: AAA\n"


@pytest.fixture(autouse=True)
def _setup_and_teardown():
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    with open(TEST_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(INITIAL_CONTENT)
    yield
    try:
        os.unlink(TEST_FILE_PATH)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_edit_file_replaces_unique_match():
    result = await edit_file.execute({"path": TEST_FILE_NAME, "oldText": "line 2: BBB", "newText": "line 2: CCC"})

    assert "ファイルを編集しました" in result
    with open(TEST_FILE_PATH, "r", encoding="utf-8") as f:
        assert f.read() == "line 1: AAA\nline 2: CCC\nline 3: AAA\n"


@pytest.mark.asyncio
async def test_edit_file_errors_when_not_found():
    with pytest.raises(ValueError, match="変更対象が見つかりません"):
        await edit_file.execute({"path": TEST_FILE_NAME, "oldText": "line X: ZZZ", "newText": "line X: YYY"})


@pytest.mark.asyncio
async def test_edit_file_errors_when_ambiguous():
    with pytest.raises(ValueError, match="複数の候補が見つかりました"):
        await edit_file.execute({"path": TEST_FILE_NAME, "oldText": "AAA", "newText": "XXX"})


@pytest.mark.asyncio
async def test_edit_file_blocks_path_traversal():
    with pytest.raises(ValueError, match="アクセス拒否"):
        await edit_file.execute({"path": "../outside.txt", "oldText": "AAA", "newText": "XXX"})


@pytest.mark.asyncio
async def test_edit_file_blocks_symlink_outside_workspace():
    symlink_name = "bad-edit-symlink.txt"
    symlink_path = os.path.join(WORKSPACE_ROOT, symlink_name)
    target_path = os.path.join(os.path.dirname(WORKSPACE_ROOT), "pyproject.toml")

    try:
        os.symlink(target_path, symlink_path)
        with pytest.raises(ValueError, match="アクセス拒否"):
            await edit_file.execute({"path": symlink_name, "oldText": "AAA", "newText": "XXX"})
    finally:
        try:
            os.unlink(symlink_path)
        except OSError:
            pass
