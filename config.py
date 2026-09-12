import os
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for HealOps Layer 1."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App Info
    APP_NAME: str = "HealOps SRE Autonomous Agent"
    ENV: Literal["development", "production", "test"] = "development"
    
    # Model Provider Selection
    MODEL_PROVIDER: Literal["bedrock", "gemini", "openai", "anthropic", "ollama", "litellm"] = "gemini"
    
    # Provider-Specific Model IDs
    BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    AWS_REGION: str = "us-east-1"
    
    GEMINI_MODEL_ID: str = "gemini-2.0-flash"
    GEMINI_API_KEY: Optional[str] = None
    
    OPENAI_MODEL_ID: str = "gpt-4o"
    OPENAI_API_KEY: Optional[str] = None
    
    ANTHROPIC_MODEL_ID: str = "claude-3-5-sonnet-20241022"
    ANTHROPIC_API_KEY: Optional[str] = None
    
    OLLAMA_MODEL_ID: str = "llama3.2"
    OLLAMA_HOST: str = "http://localhost:11434"

    # Redis Session Storage
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_NAMESPACE: str = "healops:sessions"
    SESSION_TTL_SECONDS: int = 86400  # 24 hours

    # Local Fallback Storage
    DATA_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


settings = Settings()
