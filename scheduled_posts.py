"""予約投稿: scheduled/YYYY-MM-DD.md に置いた完成記事を、その日に投稿する。

ファイル形式:
    ---
    title: 記事タイトル
    hashtags: ["タグ1", "タグ2"]
    price: 300
    ---
    無料パート本文...

    ---有料ここから---

    有料パート本文...

投稿後はファイル名末尾に .posted を付けて二重投稿を防ぐ。
"""
import os
import json
from datetime import datetime, timezone, timedelta

SCHEDULED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scheduled")
JST = timezone(timedelta(hours=9))


def _today_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%d")


def _parse_front_matter(text: str):
    """先頭の --- ... --- フロントマターを (meta_dict, body) に分解する。"""
    meta = {"title": "", "hashtags": [], "price": 0}
    body = text
    if text.lstrip().startswith("---"):
        stripped = text.lstrip()
        end = stripped.find("---", 3)
        if end != -1:
            fm = stripped[3:end].strip()
            body = stripped[end + 3:].lstrip("\n")
            for line in fm.splitlines():
                if ":" not in line:
                    continue
                key, val = line.split(":", 1)
                key, val = key.strip(), val.strip()
                if key == "hashtags":
                    try:
                        meta["hashtags"] = json.loads(val)
                    except Exception:
                        meta["hashtags"] = [
                            h.strip().strip('"') for h in val.strip("[]").split(",") if h.strip()
                        ]
                elif key == "price":
                    try:
                        meta["price"] = int(val)
                    except ValueError:
                        meta["price"] = 0
                else:
                    meta[key] = val.strip('"')
    return meta, body.strip()


def get_due_post():
    """今日(JST)の日付に対応する未投稿の予約記事を返す。なければ None。

    戻り値: (path, meta, body) または None
    """
    if not os.path.isdir(SCHEDULED_DIR):
        return None
    today = _today_jst()
    path = os.path.join(SCHEDULED_DIR, f"{today}.md")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    meta, body = _parse_front_matter(text)
    return path, meta, body


def mark_posted(path: str):
    """投稿済みとしてファイルをリネーム（二重投稿防止）。"""
    posted = path + ".posted"
    try:
        os.replace(path, posted)
    except OSError:
        pass
