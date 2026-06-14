"""NotebookLM等の素材メモ → Claude → note記事ドラフト（要レビュー）。

ワークフロー:
  1) NotebookLM で本/資料を読み込み、要点＋出典を抽出（プロンプトは source/README.md 参照）
  2) その抽出結果を source/ にテキストとして保存
  3) このスクリプトで Claude に note 記事化させる
  4) drafts/ に出来たドラフトを“人が”レビュー
  5) 問題なければ scheduled/YYYY-MM-DD.md に移すと、既存パイプラインが当日自動投稿する

使い方:
  python from_source.py source/your_material.md
  python from_source.py source/your_material.md --price 0          # 無料記事として
  python from_source.py source/your_material.md --schedule 2026-06-20   # 直接その日に予約（レビュー後推奨）

※ 公開物なので、デフォルトでは自動投稿せず drafts/ に保存するだけ。
"""
from __future__ import annotations

import os
import re
import argparse
from datetime import datetime, timezone, timedelta

from generator import generate_article_from_source
from scheduled_posts import _parse_front_matter
from config import config

JST = timezone(timedelta(hours=9))
BASE = os.path.dirname(os.path.abspath(__file__))
DRAFTS_DIR = os.path.join(BASE, "drafts")
SCHEDULED_DIR = os.path.join(BASE, "scheduled")


def _read_source(path: str) -> str:
    if not os.path.isfile(path):
        raise SystemExit(f"❌ 素材ファイルが見つかりません: {path}")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read().strip()
    if len(text) < 50:
        raise SystemExit("❌ 素材メモが短すぎます。NotebookLMの要点＋出典を貼り付けてください。")
    return text


def main():
    parser = argparse.ArgumentParser(description="NotebookLM素材メモ → note記事ドラフト生成")
    parser.add_argument("source", help="素材メモのファイルパス（NotebookLMの要点＋出典）")
    parser.add_argument("--price", type=int, default=None,
                        help=f"記事価格（円）。0で無料。未指定は config.default_price={config.default_price}")
    parser.add_argument("--schedule", metavar="YYYY-MM-DD",
                        help="この日付の予約記事として scheduled/ に直接保存（レビュー後の利用を推奨）")
    parser.add_argument("--angle", default=None,
                        help="記事の切り口・編集方針（例: 本の原則をAI活用に結びつける）。未指定なら素直に記事化")
    args = parser.parse_args()

    source = _read_source(args.source)
    print(f"📄 素材メモ読み込み: {args.source}（{len(source)}字）")
    print("🤖 Claude で note 記事を生成中…")

    file_text = generate_article_from_source(source, price=args.price, angle=args.angle)

    # --price を指定したら、生成物の価格をそれに合わせる（モデルが別の値を書くことがあるため）
    if args.price is not None:
        file_text = re.sub(r"(?m)^price:.*$", f"price: {args.price}", file_text, count=1)

    # 生成物がちゃんとフロントマター形式になっているか検証
    meta, body = _parse_front_matter(file_text)
    if not meta.get("title"):
        raise SystemExit("❌ 生成物に title がありません。素材メモを増やして再実行してください。\n--- 生成物 ---\n" + file_text[:500])

    free_body = body.split("---有料ここから---", 1)[0].strip()
    has_paywall = "---有料ここから---" in body
    paid_len = len(body) - len(free_body)

    # 保存先を決定（デフォルトは drafts/、--schedule 指定時のみ scheduled/）
    if args.schedule:
        os.makedirs(SCHEDULED_DIR, exist_ok=True)
        out_path = os.path.join(SCHEDULED_DIR, f"{args.schedule}.md")
        where = "予約投稿"
    else:
        os.makedirs(DRAFTS_DIR, exist_ok=True)
        stem = os.path.splitext(os.path.basename(args.source))[0]
        stamp = datetime.now(JST).strftime("%Y%m%d_%H%M")
        out_path = os.path.join(DRAFTS_DIR, f"from_source_{stem}_{stamp}.md")
        where = "下書き"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(file_text + "\n")

    print("\n✅ 生成完了")
    print(f"  タイトル : {meta['title']}")
    print(f"  タグ     : {meta.get('hashtags', [])}")
    print(f"  価格     : {meta.get('price', 0)}円")
    print(f"  無料パート: {len(free_body)}字 / 有料パート: {paid_len}字"
          + ("" if has_paywall else "  ⚠️ 有料ラインの区切りが見つかりません（要確認）"))
    print(f"  保存先   : {out_path}（{where}）")

    if not args.schedule:
        print("\n👀 中身を確認して問題なければ、予約投稿に回せます:")
        today = datetime.now(JST).strftime("%Y-%m-%d")
        print(f"    cp \"{out_path}\" scheduled/{today}.md   # 例: 今日の日付で予約")
        print("  → 既存パイプライン（朝8時/夜19時 JST）がその日付の記事を自動投稿します。")


if __name__ == "__main__":
    main()
