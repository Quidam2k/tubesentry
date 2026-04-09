import os
from pathlib import Path
from dataclasses import dataclass, field

import yaml


@dataclass
class WhisperConfig:
    model: str = "base"
    language: str | None = "en"


@dataclass
class ClaudeConfig:
    model: str = "claude-sonnet-4-20250514"
    api_key: str = ""

    def __post_init__(self):
        if not self.api_key:
            self.api_key = os.environ.get("ANTHROPIC_API_KEY", "")


@dataclass
class OpenAICompatibleConfig:
    base_url: str = "http://localhost:1234/v1"
    model: str = "gemma-4"
    api_key: str = "lm-studio"


@dataclass
class SummarizerConfig:
    backend: str = "claude"
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    openai_compatible: OpenAICompatibleConfig = field(default_factory=OpenAICompatibleConfig)


@dataclass
class ScannerConfig:
    initial_video_limit: int = 50
    poll_interval_minutes: int = 60


@dataclass
class AppConfig:
    download_dir: str = "./downloads"
    database_url: str = "sqlite:///./tubesentry.db"
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    summarizer: SummarizerConfig = field(default_factory=SummarizerConfig)
    scanner: ScannerConfig = field(default_factory=ScannerConfig)


def load_config(config_path: str = "config.yaml") -> AppConfig:
    """Load configuration from YAML file, falling back to defaults."""
    path = Path(config_path)
    if not path.exists():
        return AppConfig()

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    whisper_raw = raw.get("whisper", {})
    whisper = WhisperConfig(**whisper_raw)

    summarizer_raw = raw.get("summarizer", {})
    claude_raw = summarizer_raw.get("claude", {})
    openai_raw = summarizer_raw.get("openai_compatible", {})
    summarizer = SummarizerConfig(
        backend=summarizer_raw.get("backend", "claude"),
        claude=ClaudeConfig(**claude_raw),
        openai_compatible=OpenAICompatibleConfig(**openai_raw),
    )

    scanner_raw = raw.get("scanner", {})
    scanner = ScannerConfig(**scanner_raw)

    return AppConfig(
        download_dir=raw.get("download_dir", "./downloads"),
        database_url=raw.get("database_url", "sqlite:///./tubesentry.db"),
        whisper=whisper,
        summarizer=summarizer,
        scanner=scanner,
    )


# Global config instance
config = load_config()
