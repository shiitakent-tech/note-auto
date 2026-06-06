"""note.com unofficial API client (cookie-based session)."""
import json
import time
import requests
from dataclasses import dataclass
from config import config


BASE = "https://note.com/api/v2"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://note.com/",
}


@dataclass
class PostedArticle:
    key: str
    url: str
    title: str


class NoteClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.session.cookies.update(self._parse_cookie(config.note_cookie))

    @staticmethod
    def _parse_cookie(raw: str) -> dict:
        result = {}
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.strip()] = v.strip()
        return result

    def _csrf(self) -> str:
        r = self.session.get("https://note.com/")
        for line in r.text.splitlines():
            if "csrf-token" in line and "content=" in line:
                start = line.index('content="') + 9
                end = line.index('"', start)
                return line[start:end]
        return ""

    def post_article(
        self,
        title: str,
        body: str,
        price: int = 0,
        free_body: str = "",
        magazine_id: str = "",
        hashtags: list[str] | None = None,
    ) -> PostedArticle:
        csrf = self._csrf()
        payload: dict = {
            "name": title,
            "body": body,
            "status": "public",
            "price": price,
        }
        if price > 0 and free_body:
            payload["free_body"] = free_body
        if magazine_id:
            payload["magazine_id"] = magazine_id
        if hashtags:
            payload["hashtag_list"] = hashtags

        r = self.session.post(
            f"{BASE}/notes",
            json=payload,
            headers={**HEADERS, "X-CSRF-Token": csrf, "Content-Type": "application/json"},
        )
        r.raise_for_status()
        data = r.json()["data"]
        key = data["key"]
        url = f"https://note.com/{config.note_user_id}/n/{key}"
        return PostedArticle(key=key, url=url, title=title)

    def get_stats(self, limit: int = 20) -> list[dict]:
        """記事ごとのビュー数・購入数を取得。"""
        r = self.session.get(
            f"{BASE}/creators/{config.note_user_id}/contents",
            params={"kind": "note", "page": 1},
        )
        r.raise_for_status()
        notes = r.json()["data"]["contents"][:limit]
        results = []
        for n in notes:
            results.append({
                "key": n["key"],
                "title": n["name"],
                "views": n.get("noteableCount", 0),
                "likes": n.get("likeCount", 0),
                "sales": n.get("purchaseCount", 0),
                "price": n.get("price", 0),
                "url": f"https://note.com/{config.note_user_id}/n/{n['key']}",
            })
        return results

    def add_to_magazine(self, note_key: str, magazine_id: str) -> None:
        csrf = self._csrf()
        self.session.post(
            f"{BASE}/magazines/{magazine_id}/notes",
            json={"note_key": note_key},
            headers={**HEADERS, "X-CSRF-Token": csrf, "Content-Type": "application/json"},
        ).raise_for_status()
        time.sleep(0.5)
