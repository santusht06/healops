"""Model Factory for HealOps Layer 1.

Supports dynamic switching between AWS Bedrock, Google Gemini, OpenAI,
Anthropic, Ollama, and LiteLLM based on project configuration.
"""

import os
from typing import Optional
from strands.models import Model
from config import settings


def get_model(provider: Optional[str] = None) -> Model:
    """Instantiate and return the configured Strands Model instance."""
    active_provider = (provider or settings.MODEL_PROVIDER).lower()

    if active_provider == "bedrock":
        from strands.models import BedrockModel

        return BedrockModel(
            model_id=settings.BEDROCK_MODEL_ID,
            region_name=settings.AWS_REGION
        )

    elif active_provider == "gemini":
        from strands.models import GeminiModel

        api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
        client_args = {"api_key": api_key} if api_key else {}
        return GeminiModel(
            model_id=settings.GEMINI_MODEL_ID,
            client_args=client_args
        )

    elif active_provider == "openai":
        from strands.models import OpenAIModel

        api_key = settings.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
        client_args = {"api_key": api_key} if api_key else {}
        return OpenAIModel(
            model_id=settings.OPENAI_MODEL_ID,
            client_args=client_args
        )

    elif active_provider == "anthropic":
        from strands.models import AnthropicModel

        api_key = settings.ANTHROPIC_API_KEY or os.getenv("ANTHROPIC_API_KEY")
        client_args = {"api_key": api_key} if api_key else {}
        return AnthropicModel(
            model_id=settings.ANTHROPIC_MODEL_ID,
            client_args=client_args
        )

    elif active_provider == "ollama":
        from strands.models import OllamaModel

        return OllamaModel(
            host=settings.OLLAMA_HOST,
            model_id=settings.OLLAMA_MODEL_ID
        )

    elif active_provider == "litellm":
        from strands.models import LiteLLMModel

        return LiteLLMModel(
            model_id=settings.OPENAI_MODEL_ID
        )

    else:
        raise ValueError(
            f"Unsupported model provider '{active_provider}'. "
            f"Allowed: 'bedrock', 'gemini', 'openai', 'anthropic', 'ollama', 'litellm'"
        )
