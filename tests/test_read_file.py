import os

import pytest

from src.tools.read_file import WORKSPACE_ROOT, read_file

TEST_FILE_NAME = "test-read-file.txt"
TEST_FILE_PATH = os.path.join(WORKSPACE_ROOT, TEST_FILE_NAME)
TEST_CONTENT = "Hello, this is a test file for readFile tool."


@pytest.fixture(autouse=True)
def _setup_and_teardown():
    os.makedirs(WORKSPACE_ROOT, exist_ok=True)
    with open(TEST_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(TEST_CONTENT)
    yield
    try:
        os.unlink(TEST_FILE_PATH)
    except OSError:
        pass


@pytest.mark.asyncio
async def test_read_file_inside_workspace():
    result = await read_file.execute({"path": TEST_FILE_NAME})
    assert result == TEST_CONTENT


@pytest.mark.asyncio
async def test_read_file_missing():
    with pytest.raises(ValueError, match="ファイルが見つかりません"):
        await read_file.execute({"path": "non-existent-file.txt"})


@pytest.mark.asyncio
async def test_read_file_blocks_path_traversal():
    with pytest.raises(ValueError, match="アクセス拒否"):
        await read_file.execute({"path": "../pyproject.toml"})


@pytest.mark.asyncio
async def test_read_file_blocks_symlink_outside_workspace():
    symlink_name = "bad-symlink.txt"
    symlink_path = os.path.join(WORKSPACE_ROOT, symlink_name)
    target_path = os.path.join(os.path.dirname(WORKSPACE_ROOT), "pyproject.toml")

    try:
        os.symlink(target_path, symlink_path)
        with pytest.raises(ValueError, match="アクセス拒否"):
            await read_file.execute({"path": symlink_name})
    finally:
        try:
            os.unlink(symlink_path)
        except OSError:
            pass


@pytest.mark.asyncio
async def test_read_file_blocks_oversized_file():
    huge_file_name = "huge-file.txt"
    huge_file_path = os.path.join(WORKSPACE_ROOT, huge_file_name)
    huge_content = "a" * (101 * 1024)

    try:
        with open(huge_file_path, "w", encoding="utf-8") as f:
            f.write(huge_content)
        with pytest.raises(ValueError, match="ファイルが大きすぎます"):
            await read_file.execute({"path": huge_file_name})
    finally:
        try:
            os.unlink(huge_file_path)
        except OSError:
            pass
