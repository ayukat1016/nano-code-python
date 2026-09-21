import os

import pytest

from src.tools.write_file import WORKSPACE_ROOT, write_file

TEST_FILE_NAME = "test-write-file.txt"
TEST_FILE_PATH = os.path.join(WORKSPACE_ROOT, TEST_FILE_NAME)


@pytest.fixture(autouse=True)
def _teardown():
    yield
    for p in [TEST_FILE_PATH, os.path.join(WORKSPACE_ROOT, "new-dir", "nested.txt")]:
        try:
            os.unlink(p)
        except OSError:
            pass
    try:
        os.rmdir(os.path.join(WORKSPACE_ROOT, "new-dir"))
    except OSError:
        pass


@pytest.mark.asyncio
async def test_write_file_inside_workspace():
    content = "Hello, this is content written by writeFile tool."
    result = await write_file.execute({"path": TEST_FILE_NAME, "content": content})

    assert TEST_FILE_NAME in result
    with open(TEST_FILE_PATH, "r", encoding="utf-8") as f:
        assert f.read() == content


@pytest.mark.asyncio
async def test_write_file_creates_nested_directories():
    nested_path = os.path.join("new-dir", "nested.txt")
    nested_file_path = os.path.join(WORKSPACE_ROOT, nested_path)
    content = "Nested content"

    result = await write_file.execute({"path": nested_path, "content": content})

    assert nested_path in result
    with open(nested_file_path, "r", encoding="utf-8") as f:
        assert f.read() == content


@pytest.mark.asyncio
async def test_write_file_blocks_path_traversal():
    with pytest.raises(ValueError, match="アクセス拒否"):
        await write_file.execute({"path": "../outside.txt", "content": "attempt"})


@pytest.mark.asyncio
async def test_write_file_blocks_symlink_outside_workspace():
    symlink_name = "bad-write-symlink.txt"
    symlink_path = os.path.join(WORKSPACE_ROOT, symlink_name)
    target_path = os.path.join(os.path.dirname(WORKSPACE_ROOT), "pyproject.toml")

    try:
        os.symlink(target_path, symlink_path)
        with pytest.raises(ValueError, match="アクセス拒否"):
            await write_file.execute({"path": symlink_name, "content": "malicious attempt"})
    finally:
        try:
            os.unlink(symlink_path)
        except OSError:
            pass
