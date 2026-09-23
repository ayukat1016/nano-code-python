import pytest

from src.tools.git_tools import commit, create_branch, push_branch


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "branch_name",
    [
        "",
        "feature branch",
        "-feature",
        ":feature",
        "feature;rm -rf /",
        "feature/../../etc",
        "feature//x",
        "feature/",
        "feature.",
    ],
)
async def test_create_branch_rejects_invalid_names(branch_name):
    with pytest.raises(ValueError):
        await create_branch.execute({"branchName": branch_name})


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "branch_name",
    ["", "feature branch", "-feature", "feature;rm -rf /"],
)
async def test_push_branch_rejects_invalid_names(branch_name):
    with pytest.raises(ValueError):
        await push_branch.execute({"branchName": branch_name})


@pytest.mark.asyncio
async def test_commit_rejects_empty_message():
    with pytest.raises(ValueError, match="コミットメッセージが不正です"):
        await commit.execute({"message": "", "files": []})


@pytest.mark.asyncio
async def test_commit_rejects_null_byte_message():
    with pytest.raises(ValueError, match="コミットメッセージが不正です"):
        await commit.execute({"message": "bad\0message", "files": []})
