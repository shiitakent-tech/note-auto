"""セッションCookieからnote_gql_auth_tokenを自動取得するスクリプト。"""
import os
import sys
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()


def get_gql_auth_token(session_cookie: str) -> str:
    """Playwrightを使ってnote_gql_auth_tokenを取得する。"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # セッションCookieをセット
        for part in session_cookie.split(";"):
            part = part.strip()
            if "=" in part:
                name, value = part.split("=", 1)
                context.add_cookies([{
                    "name": name.strip(),
                    "value": value.strip(),
                    "domain": ".note.com",
                    "path": "/",
                }])

        page = context.new_page()
        # プロフィールページにアクセスしてJSにトークンを発行させる
        from config import config as _cfg
        page.goto(f"https://note.com/{_cfg.note_user_id}", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # note_gql_auth_tokenを取得
        cookies = context.cookies()
        token = next(
            (c["value"] for c in cookies if c["name"] == "note_gql_auth_token"),
            None
        )

        browser.close()

        if not token:
            raise RuntimeError("note_gql_auth_tokenが取得できませんでした。セッションCookieが有効か確認してください。")

        return token


if __name__ == "__main__":
    session_cookie = os.environ.get("NOTE_COOKIE", "")
    if not session_cookie:
        print("ERROR: NOTE_COOKIEが設定されていません", file=sys.stderr)
        sys.exit(1)

    token = get_gql_auth_token(session_cookie)
    print(token)
