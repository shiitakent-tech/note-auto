"""Pexels APIで見出し画像を検索・ダウンロードする。"""
import tempfile
from typing import Optional
import requests
import anthropic
from config import config


def _extract_image_keywords(title: str) -> str:
    """記事タイトルからPexels検索用の英語キーワードを抽出する。"""
    client = anthropic.Anthropic(api_key=config.anthropic_api_key)
    msg = client.messages.create(
        model=config.claude_model,
        max_tokens=30,
        messages=[{
            "role": "user",
            "content": (
                "Extract 2-3 English keywords for a Pexels stock photo search "
                "based on this Japanese article title. "
                "Return only keywords separated by spaces, no explanation.\n"
                f"Title: {title}"
            ),
        }],
    )
    return msg.content[0].text.strip()


def fetch_header_image(title: str) -> Optional[str]:
    """Pexelsで見出し画像を取得し、一時ファイルパスを返す。

    PEXELS_API_KEY が未設定またはエラー時は None を返す（投稿は継続）。
    """
    if not config.pexels_api_key:
        return None

    try:
        keywords = _extract_image_keywords(title)
        print(f"  🔍 Pexels検索キーワード: {keywords}")

        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": config.pexels_api_key},
            params={"query": keywords, "per_page": 1, "orientation": "landscape"},
            timeout=10,
        )
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if not photos:
            print("  ⚠️  Pexels: 画像が見つかりませんでした")
            return None

        image_url = photos[0]["src"].get("large2x") or photos[0]["src"]["original"]
        img_r = requests.get(image_url, timeout=30)
        img_r.raise_for_status()

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(img_r.content)
        tmp.close()
        print(f"  ✅ Pexels画像取得完了")
        return tmp.name

    except Exception as e:
        print(f"  ⚠️  Pexels画像取得エラー: {e}")
        return None
