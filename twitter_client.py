"""X (Twitter) API v2 client."""
import tweepy
from config import config


def get_client() -> tweepy.Client | None:
    if not all([
        config.twitter_api_key,
        config.twitter_api_secret,
        config.twitter_access_token,
        config.twitter_access_secret,
    ]):
        return None
    return tweepy.Client(
        consumer_key=config.twitter_api_key,
        consumer_secret=config.twitter_api_secret,
        access_token=config.twitter_access_token,
        access_token_secret=config.twitter_access_secret,
    )


def tweet(text: str) -> str | None:
    client = get_client()
    if client is None:
        print("[Twitter] 認証情報が未設定のためスキップ")
        return None
    resp = client.create_tweet(text=text)
    tweet_id = resp.data["id"]
    return f"https://x.com/i/web/status/{tweet_id}"
