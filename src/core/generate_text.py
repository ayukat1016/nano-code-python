"""非ストリーミングのテキスト生成呼び出し。"""
from __future__ import annotations

from typing import Optional

from ..types import GenerateParams, GenerateTextResult, LanguageModel, Message, Tool


async def generate_text(
    model: LanguageModel,
    messages: list[Message],
    tools: Optional[list[Tool]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> GenerateTextResult:
    return await model.do_generate(
        GenerateParams(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    )
