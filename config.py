import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    """
    Application settings for the MangaMotive Agentic Worker Pipeline.
    Loads configuration from environment variables or .env file.
    """
    # Ollama Local Runtime Settings
    ollama_base_url: str = Field(default="http://127.0.0.1:11434", description="Base URL for local Ollama instance")
    ollama_default_model: str = Field(default="gemma:2b", description="Default small LLM optimized for Raspberry Pi 5")
    ollama_timeout_seconds: int = Field(default=120, description="Timeout for LLM generation requests")

    # Contentful Management API Settings
    contentful_management_token: str = Field(default="cfp_placeholder_token", description="Contentful Management API Token")
    contentful_space_id: str = Field(default="placeholder_space_id", description="Contentful Space ID")
    contentful_environment_id: str = Field(default="master", description="Contentful Environment ID")

    # AnimeSchedule API Settings
    animeschedule_api_key: str = Field(default="your_api_key_here", description="API Key for AnimeSchedule.net")

    # Storage & Queue Settings
    database_url: str = Field(default="sqlite:///./data/agent_memory.db", description="SQLite database URL for agent memory")
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL for Celery/Task queuing")

    # Agent Operational Settings
    log_level: str = Field(default="INFO", description="Logging level (INFO, DEBUG, WARNING, ERROR)")
    dry_run: bool = Field(default=True, description="If True, skips actual Contentful publishing and logs output instead")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
