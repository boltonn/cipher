import asyncio

import httpx


async def test_stream():
    """A simple test to demonstrate how to consume the streaming endpoint."""
    url = "http://localhost:8000/chat"  # Update to your actual host/port

    # Mock Vercel AI SDK body
    payload = {
        "messages": [{"role": "user", "content": "What is in this dataset?"}],
        # We pass the dataset_id in the body so the agent can use it
        "data": {"dataset_id": "YOUR_ACTUAL_UUID_HERE"},
    }

    async with (
        httpx.AsyncClient() as client,
        client.stream("POST", url, json=payload, timeout=None) as response,
    ):
        async for line in response.aiter_lines():
            if line:
                # The Vercel adapter sends prefixed lines like '0:"text"' or '9:{"tool"...}'
                print(line)


if __name__ == "__main__":
    asyncio.run(test_stream())
