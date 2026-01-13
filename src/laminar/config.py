"""Configuration management using pydantic-settings."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="LAMINAR_",
        extra="ignore",
    )

    # Anthropic/Claude Configuration
    anthropic_api_key: Annotated[
        SecretStr,
        Field(description="Anthropic API key for Claude analysis"),
    ] = SecretStr("")

    claude_model: Annotated[
        str,
        Field(description="Claude model to use for analysis"),
    ] = "claude-sonnet-4-20250514"

    claude_max_tokens: Annotated[
        int,
        Field(ge=1, le=64000, description="Maximum tokens for Claude response"),
    ] = 8192

    claude_temperature: Annotated[
        float,
        Field(ge=0.0, le=1.0, description="Temperature for Claude response"),
    ] = 0.0

    # Excel Processing Mode
    excel_mode: Annotated[
        Literal["image", "csv", "both"],
        Field(description="How to process Excel files: image, csv, or both"),
    ] = "both"

    # Docker Configuration
    docker_image: Annotated[
        str,
        Field(description="Docker image for XLSX to PNG conversion"),
    ] = "xls2png-converter"

    # Path Configuration
    output_dir: Annotated[
        Path,
        Field(description="Default output directory"),
    ] = Path("output")

    sample_json_path: Annotated[
        Path,
        Field(description="Path to sample JSON template"),
    ] = Path("sample.json")

    sample_image_path: Annotated[
        Path,
        Field(description="Path to sample image"),
    ] = Path("sample.png")

    # Logging Configuration
    log_level: Annotated[
        str,
        Field(description="Logging level"),
    ] = "INFO"

    log_file: Annotated[
        Path | None,
        Field(description="Log file path (None for stdout only)"),
    ] = None

    @property
    def has_api_key(self) -> bool:
        """Check if a valid API key is configured."""
        key = self.anthropic_api_key.get_secret_value()
        return bool(key and key != "<your key>")


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()


def update_api_key(api_key: str) -> None:
    """Update the Anthropic API key and clear the settings cache.

    Args:
        api_key: The new API key to set.
    """
    # Clear the cache to force reload
    get_settings.cache_clear()

    # Write to .env file for persistence
    env_path = Path(".env")
    env_content = ""

    if env_path.exists():
        env_content = env_path.read_text()
        # Remove existing LAMINAR_ANTHROPIC_API_KEY line if present
        lines = [
            line
            for line in env_content.splitlines()
            if not line.startswith("LAMINAR_ANTHROPIC_API_KEY=")
        ]
        env_content = "\n".join(lines)
        if env_content and not env_content.endswith("\n"):
            env_content += "\n"

    env_content += f"LAMINAR_ANTHROPIC_API_KEY={api_key}\n"
    env_path.write_text(env_content)
