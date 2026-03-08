import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _required_env(name: str) -> str:
    value = (os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


endpoint = _required_env("AZURE_OPENAI_ENDPOINT").rstrip("/")
api_key = _required_env("AZURE_OPENAI_API_KEY")
deployment = _required_env("MODEL")

client = OpenAI(
    api_key=api_key,
    base_url=f"{endpoint}/openai/v1/",
)

response = client.responses.create(
    model=deployment,
    input=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how are you?"},
    ],
)

print(response.output_text)
