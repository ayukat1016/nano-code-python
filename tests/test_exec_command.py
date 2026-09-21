import pytest

from src.tools.exec_command import exec_command


@pytest.mark.asyncio
async def test_runs_allowed_command_successfully():
    result = await exec_command.execute({"command": "ls"})
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_blocks_command_not_in_allowed_list():
    with pytest.raises(ValueError, match="許可されていません"):
        await exec_command.execute({"command": "whoami"})


@pytest.mark.asyncio
async def test_blocks_shell_metacharacters():
    for command in ["ls; whoami", "ls & whoami", "ls `whoami`", "ls $(whoami)", "ls | whoami"]:
        with pytest.raises(ValueError, match="シェルメタ文字を含むコマンドは実行できません"):
            await exec_command.execute({"command": command})


@pytest.mark.asyncio
async def test_blocks_dangerous_pattern_commands():
    with pytest.raises(ValueError, match="危険なコマンドパターンが検出されました"):
        await exec_command.execute({"command": "ls --flag rm -rf"})


@pytest.mark.asyncio
async def test_blocks_command_with_dangerous_options():
    # find -exec の検知（メタ文字セミコロンを含むためメタ文字エラーになる）
    with pytest.raises(ValueError, match="シェルメタ文字を含むコマンドは実行できません"):
        await exec_command.execute({"command": "find . -exec rm -rf {} \\;"})

    # find -delete の検知
    with pytest.raises(ValueError, match="危険なコマンドパターンが検出されました"):
        await exec_command.execute({"command": "find . -delete"})

    # git --git-dir の検知
    with pytest.raises(ValueError, match="危険なコマンドパターンが検出されました"):
        await exec_command.execute({"command": "git --git-dir=../.git status"})

    # git --work-tree の検知
    with pytest.raises(ValueError, match="危険なコマンドパターンが検出されました"):
        await exec_command.execute({"command": "git --work-tree=/tmp status"})


@pytest.mark.asyncio
async def test_blocks_arguments_outside_workspace():
    with pytest.raises(ValueError, match="アクセス拒否"):
        await exec_command.execute({"command": "ls ../"})
    with pytest.raises(ValueError, match="アクセス拒否"):
        await exec_command.execute({"command": "ls /etc"})


@pytest.mark.asyncio
async def test_raises_on_nonzero_exit_code():
    with pytest.raises(RuntimeError, match="コマンドが異常終了しました"):
        await exec_command.execute({"command": "ls non-existent-file-xyz"})
