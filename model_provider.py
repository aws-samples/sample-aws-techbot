# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Model provider selection with caching and dynamic config reload.

Supports: Bedrock, OpenAI-compatible (Zhipu, Deepseek, SiliconFlow, etc.),
Anthropic, Gemini, and Ollama.

Config is read from environment variables + Secrets Manager.
Users can change model settings in Secrets Manager without restarting Runtime.
"""

import os
import time
import logging

from strands.models import BedrockModel

logger = logging.getLogger("techbot")

_model_cache = {"model": None, "model_id": None, "expires_at": 0}
_MODEL_CACHE_TTL = 300  # 5 minutes


def _get_model_config(region: str):
    """Read model config from Secrets Manager or environment variables."""
    model_provider = os.getenv("MODEL_PROVIDER", "bedrock")
    model_id = os.getenv("MODEL_ID")
    base_url = os.getenv("MODEL_BASE_URL")

    api_key = os.getenv("MODEL_API_KEY")
    if not api_key and model_provider != "bedrock":
        secret_arn = os.getenv("MODEL_API_KEY_SECRET_ARN")
        if secret_arn:
            import boto3
            import json
            sm = boto3.client("secretsmanager", region_name=region)
            secret_value = sm.get_secret_value(SecretId=secret_arn)["SecretString"]
            try:
                secret_data = json.loads(secret_value)
                api_key = secret_data.get("api_key", secret_value)
                model_id = secret_data.get("model_id", model_id)
                base_url = secret_data.get("base_url", base_url)
            except (json.JSONDecodeError, AttributeError):
                api_key = secret_value

    return model_provider, model_id, api_key, base_url


def get_model(region: str):
    """Get or create model instance with caching (TTL 5 min)."""
    now = time.time()
    if _model_cache["model"] and now < _model_cache["expires_at"]:
        return _model_cache["model"], _model_cache["model_id"]

    model_provider, model_id, api_key, base_url = _get_model_config(region)

    if model_provider == "bedrock":
        model = BedrockModel(model_id=model_id)
    elif model_provider == "anthropic":
        from strands.models.anthropic import AnthropicModel
        model = AnthropicModel(api_key=api_key, model_id=model_id)
    elif model_provider == "gemini":
        from strands.models.gemini import GeminiModel
        model = GeminiModel(api_key=api_key, model_id=model_id)
    elif model_provider == "ollama":
        from strands.models.ollama import OllamaModel
        model = OllamaModel(host=base_url or "http://localhost:11434", model_id=model_id)
    else:  # openai-compatible (covers most third-party APIs)
        from strands.models.openai import OpenAIModel
        model = OpenAIModel(
            client_args={
                "api_key": api_key,
                "base_url": base_url,
            },
            model_id=model_id,
        )

    _model_cache["model"] = model
    _model_cache["model_id"] = model_id
    _model_cache["expires_at"] = now + _MODEL_CACHE_TTL

    logger.info(f"📍 Model: {model_provider}/{model_id}")
    return model, model_id
