from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


async def parse_openai_structured(
    *,
    api_key: str,
    model: str,
    system: str,
    user: str,
    response_model: type[T],
    temperature: float,
) -> T:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    completion = await client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=response_model,
        temperature=temperature,
    )
    message = completion.choices[0].message
    if message.parsed is not None:
        return message.parsed
    return response_model.model_validate_json(message.content or "{}")
