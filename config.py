"""Configuration — copy .env.example to .env and fill in values."""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    # note.com
    note_cookie: str = field(default_factory=lambda: os.environ["NOTE_COOKIE"])
    note_user_id: str = field(default_factory=lambda: os.environ["NOTE_USER_ID"])

    # Claude (Anthropic)
    anthropic_api_key: str = field(default_factory=lambda: os.environ["ANTHROPIC_API_KEY"])
    claude_model: str = "claude-opus-4-8"

    # X (Twitter)
    twitter_api_key: str = field(default_factory=lambda: os.getenv("TWITTER_API_KEY", ""))
    twitter_api_secret: str = field(default_factory=lambda: os.getenv("TWITTER_API_SECRET", ""))
    twitter_access_token: str = field(default_factory=lambda: os.getenv("TWITTER_ACCESS_TOKEN", ""))
    twitter_access_secret: str = field(default_factory=lambda: os.getenv("TWITTER_ACCESS_SECRET", ""))

    # Article settings
    default_price: int = 300          # 有料記事のデフォルト価格（円）
    free_part_chars: int = 500        # 無料で読める文字数
    topics_per_run: int = 3           # 1回の実行で生成する記事数
    magazine_id: str = field(default_factory=lambda: os.getenv("NOTE_MAGAZINE_ID", ""))


config = Config()
