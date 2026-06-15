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

    @staticmethod
    def _strip_md(line: str) -> str:
        """Markdown記号を除去してプレーンテキストにする（ブロック照合用）。"""
        import re
        line = re.sub(r"^[#>\-\*\+\s]+", "", line)   # 行頭の見出し/リスト記号
        line = re.sub(r"[\*_`~#]", "", line)            # インライン装飾
        return line.strip()

    def post_article(
        self,
        title: str,
        body: str,
        price: int = 0,
        free_body: str = "",
        magazine_id: str = "",
        hashtags: Optional[list] = None,
        header_image_path: Optional[str] = None,
    ) -> "PostedArticle":
        """Playwrightでエディターを操作して記事を公開する。

        price>0 かつ有料パートがある場合は有料記事として公開する。
        """
        # ── 無料パート / 有料パートを分離 ──
        marker = "---有料ここから---"
        if marker in body:
            free_part, paid_part = (s.strip() for s in body.split(marker, 1))
        else:
            free_part, paid_part = body.strip(), ""

        is_paid = price > 0 and bool(paid_part)

        # エディターに貼り付ける本文（マーカーは除去し、純粋な本文を連結）
        if paid_part:
            paste_content = free_part + "\n\n" + paid_part
        else:
            paste_content = free_part

        # 有料ライン位置を特定するための「有料パート先頭ブロック」のプレーンテキスト
        first_paid_plain = ""
        if is_paid:
            for ln in paid_part.splitlines():
                p = self._strip_md(ln)
                if p:
                    first_paid_plain = p[:18]
                    break

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

            # ── Step 2.5: 見出し画像をアップロード ──
            # hidden な input[type=file][accept*=image] を直接操作する。
            # ボタンクリックは行わない（誤ったナビゲーションを防ぐため）。
            if header_image_path:
                print("  🖼️  見出し画像をアップロード中...")
                try:
                    uploaded = False
                    file_inputs = page.locator('input[type="file"]')
                    for i in range(file_inputs.count()):
                        inp = file_inputs.nth(i)
                        accept = inp.get_attribute("accept") or ""
                        if "image" in accept:
                            inp.set_input_files(header_image_path)
                            page.wait_for_timeout(3000)
                            uploaded = True
                            break
                    if uploaded:
                        print("  ✅ 見出し画像アップロード完了")
                    else:
                        print("  ⚠️  見出し画像: image input が見つかりません（スキップ）")
                except Exception as e:
                    print(f"  ⚠️  見出し画像アップロードをスキップ: {e}")

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
                paste_content,
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
                    paste_content,
                )
                page.wait_for_timeout(2000)

            # ── Step 5: 自動保存を待つ ──
            print("  💾 自動保存待ち...")
            page.wait_for_timeout(4000)

            # ── Step 6: 「公開に進む」クリック ──
            print("  🚀 公開ダイアログを開く...")
            page.get_by_role("button", name="公開に進む").click()
            page.wait_for_timeout(4000)

            # ── Step 6.5: 有料記事の設定 ──
            if is_paid:
                print(f"  💰 有料記事に設定中（{price}円）...")
                # 「有料」ラジオを選択
                page.get_by_text("有料", exact=True).click()
                page.wait_for_timeout(2500)

                # 本人情報モーダルが出た場合は中断（登録未完了）
                if "本人情報" in page.evaluate("() => document.body.innerText"):
                    raise RuntimeError(
                        "有料化に失敗: note.comの本人情報登録が未完了です。"
                        "ブラウザで氏名・住所を登録してください。"
                    )

                # 価格を入力（デフォルト300だが明示的にセット）
                price_input = page.locator('input[placeholder="300"]')
                if price_input.count() > 0:
                    price_input.first.click()
                    price_input.first.fill(str(price))
                    page.wait_for_timeout(500)

                # 「有料エリア設定」をクリックして境界線設定画面へ
                page.get_by_role("button", name="有料エリア設定").click()
                page.wait_for_timeout(3000)

                # 有料パート先頭ブロックの直前のラインボタンをクリック
                if first_paid_plain:
                    result = page.evaluate(
                        """(target) => {
                            const blocks = Array.from(
                                document.querySelectorAll('h1,h2,h3,h4,p,li,blockquote')
                            );
                            const block = blocks.find(
                                el => el.textContent.trim().startsWith(target)
                            );
                            if (!block) return 'BLOCK_NOT_FOUND';
                            let prev = block.previousElementSibling;
                            let steps = 0;
                            while (prev && steps < 6) {
                                const btn = prev.tagName === 'BUTTON'
                                    ? prev : prev.querySelector('button');
                                if (btn && btn.textContent.includes('ラインをこの場所に変更')) {
                                    btn.click();
                                    return 'CLICKED';
                                }
                                prev = prev.previousElementSibling;
                                steps++;
                            }
                            return 'NO_BUTTON';
                        }""",
                        first_paid_plain,
                    )
                    print(f"  🔖 有料ライン設定: {result}")
                    if result == "CLICKED":
                        page.wait_for_timeout(1500)
                    else:
                        # 境界が特定できない場合、デフォルト位置（1段落目後）のまま進むと
                        # ほぼ全文が有料になり危険なので中断
                        raise RuntimeError(
                            f"有料ライン位置を特定できませんでした（{result}）。"
                            f"目印テキスト: '{first_paid_plain}'"
                        )

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
        """記事ごとのビュー数・いいね数を取得。

        note APIはGitHub Actions等のサーバーIPから403を返すことがある。
        統計はテーマ選定の補助データに過ぎないため、取得失敗時は空リストを
        返してパイプライン全体は止めない。最大3回までリトライする。
        """
        last_err = None
        for attempt in range(3):
            try:
                r = self.session.get(
                    f"{BASE_V2}/creators/{config.note_user_id}/contents",
                    params={"kind": "note", "page": 1},
                    timeout=20,
                )
                r.raise_for_status()
                notes = r.json()["data"]["contents"][:limit]
                break
            except Exception as e:  # noqa: BLE001 (403/タイムアウト等を許容)
                last_err = e
                time.sleep(3 * (attempt + 1))
        else:
            print(f"  ⚠️ 統計取得に失敗（{last_err}）。空データで続行します。")
            return []

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
