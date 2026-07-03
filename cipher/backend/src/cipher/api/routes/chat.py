import json

from fastapi import APIRouter, Header, HTTPException
from pydantic_ai import Agent
from pydantic_ai.ui.vercel_ai import VercelAIAdapter
from starlette.requests import Request
from starlette.responses import Response

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
)

agent = Agent(
    "openai:gpt-4o-mini",
    instructions="You are a helpful assistant.",
    defer_model_check=True,
)


@agent.tool_plain
def get_weather(city: str) -> str:
    """Get the current weather for a city."""
    mock_data = {"london": "15°C, cloudy", "new york": "22°C, sunny"}
    return mock_data.get(city.lower(), f"No data for {city}")


def get_model(provider: str, model_name: str, api_key: str):
    if provider == "openai":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        return OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=api_key))
    elif provider == "anthropic":
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        return AnthropicModel(model_name, provider=AnthropicProvider(api_key=api_key))
    elif provider == "google":
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        return GoogleModel(model_name, provider=GoogleProvider(api_key=api_key))
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")


@router.post("/")
async def chat(request: Request, x_api_key: str = Header(...)) -> Response:
    print(x_api_key)
    if not x_api_key.strip():
        raise HTTPException(status_code=401, detail="API key is required")

    raw_body = await request.body()
    body = json.loads(raw_body)

    model_id = body.get("model", "openai:gpt-4o-mini")
    provider, model_name = model_id.split(":", 1)
    model = get_model(provider, model_name, x_api_key)

    run_input = VercelAIAdapter.build_run_input(raw_body)
    adapter = VercelAIAdapter(
        agent=agent,
        run_input=run_input,
    )
    event_stream = adapter.run_stream(model=model)

    return adapter.streaming_response(event_stream)
