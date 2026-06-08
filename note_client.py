"""note.com client — Playwrightでエディター経由で記事を公開する。"""
import json
import time
import requests
from dataclasses import dataclass
from typing import Optional
from playwright.sync_api import sync_playwright
from config import config


BASE_V2 = "https://note.com/api/v2"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
}


@dataclass
class PostedArticle:
    key: str
    url: str
    title: str


class NoteClient:
    def __init__(self):
        self._session_cookie = config.note_cookie
        # 統計取得用のrequestsセッション（トークン不要）
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        cookies = self._parse_cookie(config.note_cookie)
        self.session.cookies.update(cookies)

    @staticmethod
    def _parse_cookie(raw: str) -> dict:
        result = {}
        for part in raw.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.strip()] = v.strip()
        return result

    def post_article(
        self,
        title: str,
        body: str,
        price: int = 0,
        free_body: str = "",
        magazine_id: str = "",
        hashtags: Optional[list] = None,
    ) -> "PostedArticle":
        """Playwrightでエディターを操作して記事を公開する。"""
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            )
            # セッションCookieをセット
            for name, val in self._parse_cookie(self._session_cookie).items():
                context.add_cookies(
                    [{"name": name, "value": val, "domain": ".note.com", "path": "/"}]
                )

            page = context.new_page()

            # ── Step 1: note.comを先に訪問してJWTトークンを発行させる ──
            print("  🌐 note.com認証中...")
            page.goto(
                f"https://note.com/{config.note_user_id}",
                wait_until="networkidle",
                timeout=30000,
            )
            page.wait_for_timeout(2000)

            # ── Step 2: エディターを開く ──
            print("  ✏️  エディター起動中...")
            page.goto(
                "https://editor.note.com/new",
                wait_until="networkidle",
                timeout=30000,
            )
            page.wait_for_timeout(3000)

            # ── Step 3: タイトルを入力（TEXTAREA） ──
            title_area = page.locator('textarea[placeholder="記事タイトル"]')
            title_area.click()
            title_area.fill(title)
            page.wait_for_timeout(500)

            # ── Step 4: 本文を入力（ProseMirror） ──
            body_editor = page.locator(
                'div.ProseMirror[contenteditable="true"]'
            )
            body_editor.click()
            page.wait_for_timeout(500)

            # クリップボード経由で長文を高速ペースト
            page.evaluate(
                """(text) => {
                    const dt = new DataTransfer();
                    dt.setData('text/plain', text);
                    document.activeElement.dispatchEvent(
                        new ClipboardEvent('paste', {clipboardData: dt, bubbles: true})
                    );
                }""",
                body,
            )
            page.wait_for_timeout(2000)

            # クリップボードが使えない場合のフォールバック: execCommand
            current_body = body_editor.inner_text()
            if len(current_body.strip()) < 10:
                page.evaluate(
                    """(text) => {
                        const editor = document.querySelector('div.ProseMirror[contenteditable="true"]');
                        if (editor) {
                            editor.focus();
                            document.execCommand('selectAll', false, null);
                            document.execCommand('insertText', false, text);
                        }
                    }""",
                    body,
                )
                page.wait_for_timeout(2000)

            # ── Step 5: 自動保存を待つ ──
            print("  💾 自動保存待ち...")
            page.wait_for_timeout(4000)

            # ── Step 6: 「公開に進む」クリック ──
            print("  🚀 公開ダイアログを開く...")
            page.get_by_role("button", name="公開に進む").click()
            page.wait_for_timeout(4000)

            # ── Step 7: 公開モーダルのボタンを特定してクリック ──
            # note.comは「投稿する」ボタンが公開モーダル内に出る
            post_btn = None
            for label in ["投稿する", "公開する", "公開", "Publish"]:
                candidate = page.locator(f'button:has-text("{label}")')
                if candidate.count() > 0:
                    post_btn = candidate.first
                    print(f"  ✅ 「{label}」ボタンを発見")
                    break

            if post_btn is None:
                # デバッグ: ボタン一覧を出力
                btns = [b.inner_text().strip() for b in page.locator("button").all() if b.inner_text().strip()]
                raise RuntimeError(f"投稿ボタンが見つかりません。ボタン一覧: {btns}")

            post_btn.click()
            print("  ⏳ 投稿処理中...")
            page.wait_for_timeout(6000)

            # ── Step 8: 投稿後URLからノートキーを取得 ──
            current_url = page.url
            print(f"  📍 投稿後URL: {current_url}")
            note_key = None

            # パターン1: https://note.com/notes/{key}/first_post
            if "/notes/" in current_url:
                parts = current_url.split("/notes/")
                if len(parts) > 1:
                    note_key = parts[1].split("/")[0]

            # パターン2: like_reaction_setting など公開後リダイレクトページの場合
            # → APIから最新記事を取得（投稿直後なので先頭が今の記事）
            if not note_key:
                time.sleep(3)
                r = self.session.get(
                    f"{BASE_V2}/creators/{config.note_user_id}/contents",
                    params={"kind": "note", "page": 1},
                )
                if r.ok:
                    contents = r.json().get("data", {}).get("contents", [])
                    # 下書き(status!="draft")を除いて最新公開記事を取得
                    for c in contents:
                        if c.get("status") != "draft":
                            note_key = c["key"]
                            break
                    if not note_key and contents:
                        note_key = contents[0]["key"]

            browser.close()

        if not note_key:
            raise RuntimeError("記事キーの取得に失敗しました")

        url = f"https://note.com/{config.note_user_id}/n/{note_key}"
        return PostedArticle(key=note_key, url=url, title=title)

    def get_stats(self, limit: int = 20) -> list:
        """記事ごとのビュー数・いいね数を取得。"""
        r = self.session.get(
            f"{BASE_V2}/creators/{config.note_user_id}/contents",
            params={"kind": "note", "page": 1},
        )
        r.raise_for_status()
        notes = r.json()["data"]["contents"][:limit]
        results = []
        for n in notes:
            results.append(
                {
                    "key": n["key"],
                    "title": n["name"],
                    "views": n.get("noteableCount", 0),
                    "likes": n.get("likeCount", 0),
                    "sales": n.get("purchaseCount", 0),
                    "price": n.get("price", 0),
                    "url": f"https://note.com/{config.note_user_id}/n/{n['key']}",
                }
            )
        return results
