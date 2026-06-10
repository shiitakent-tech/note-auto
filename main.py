"""メインパイプライン: 分析 → テーマ選定 → 記事生成 → 投稿 → SNS宣伝。"""
import os
import time
import argparse
from datetime import datetime, timezone, timedelta
from note_client import NoteClient
from generator import suggest_topics, generate_article, generate_tweet
from twitter_client import tweet
from analytics import run_report
from config import config
from scheduled_posts import get_due_post, mark_posted
from image_fetcher import fetch_header_image

JST = timezone(timedelta(hours=9))


def _auto_price() -> int:
    """投稿時間(JST)で価格を決める。朝は無料で集客、夜は有料で収益化。

    12時より前 → 無料(0円) / 12時以降 → 有料(config.default_price)
    """
    hour = datetime.now(JST).hour
    return 0 if hour < 12 else config.default_price


def _post_scheduled(note, due, dry_run: bool) -> bool:
    """予約記事を投稿する。投稿したら True を返す。"""
    path, meta, body = due
    title = meta.get("title", "（無題）")
    hashtags = meta.get("hashtags", [])
    price = meta.get("price", config.default_price)
    free_body = body.split("---有料ここから---", 1)[0].strip()

    print(f"\n📌 予約投稿を検出: {title}")
    if dry_run:
        paid_len = len(body) - len(free_body)
        print(f"  [DRY RUN] 予約投稿スキップ（無料 {len(free_body)}字 / 残り {paid_len}字 / {price}円）")
        return True

    print("  🖼️  見出し画像を検索中...")
    header_image = fetch_header_image(title)

    print("  📤 note へ投稿中...")
    article = note.post_article(
        title=title,
        body=body,
        price=price,
        free_body=free_body,
        magazine_id=config.magazine_id,
        hashtags=hashtags,
        header_image_path=header_image,
    )
    if header_image:
        os.unlink(header_image)
    print(f"  ✅ 投稿完了: {article.url}")
    mark_posted(path)  # 二重投稿防止

    print("  🐦 X へ宣伝投稿中...")
    tweet_text = generate_tweet(article.title, article.url, hashtags)
    tweet_url = tweet(tweet_text)
    if tweet_url:
        print(f"  ✅ ツイート: {tweet_url}")
    return True


def run_pipeline(dry_run: bool = False, count=None, price=None):
    note = NoteClient()
    n = count or config.topics_per_run

    # 価格: 明示指定がなければ投稿時間(JST)で自動判定（朝=無料 / 夜=有料）
    post_price = price if price is not None else _auto_price()
    mode = "無料（集客）" if post_price == 0 else f"有料 {post_price}円"
    print(f"🕐 この回の投稿モード: {mode}")

    # 今日(JST)の予約記事があれば、AI生成より優先して投稿する
    due = get_due_post()
    if due is not None:
        _post_scheduled(note, due, dry_run)
        print("\n🎉 完了: 予約記事を投稿しました")
        return

    print("📊 パフォーマンス分析中...")
    stats = note.get_stats(limit=30)

    print(f"🤖 テーマ {n} 件を選定中...")
    topics = suggest_topics(stats, n=n)

    results = []
    for i, topic in enumerate(topics, 1):
        print(f"\n✍️  [{i}/{n}] 記事生成: {topic['title']}")
        free_body, paid_body = generate_article(topic)
        full_body = f"{free_body}\n\n---有料ここから---\n\n{paid_body}"

        if dry_run:
            print(f"  [DRY RUN] 投稿スキップ（{mode}）")
            print(f"  無料パート ({len(free_body)}文字) + 有料パート ({len(paid_body)}文字)")
            results.append({"topic": topic, "skipped": True})
            continue

        print(f"  🖼️  見出し画像を検索中...")
        header_image = fetch_header_image(topic["title"])

        print(f"  📤 note へ投稿中...")
        # 無料投稿(price=0)なら全文公開、有料(price>0)なら有料ラインを設定
        article = note.post_article(
            title=topic["title"],
            body=full_body,
            price=post_price,
            free_body=free_body,
            magazine_id=config.magazine_id,
            hashtags=topic.get("hashtags", []),
            header_image_path=header_image,
        )
        if header_image:
            os.unlink(header_image)
        print(f"  ✅ 投稿完了: {article.url}")

        print(f"  🐦 X へ宣伝投稿中...")
        tweet_text = generate_tweet(article.title, article.url, topic.get("hashtags", []))
        tweet_url = tweet(tweet_text)
        if tweet_url:
            print(f"  ✅ ツイート: {tweet_url}")

        results.append({"topic": topic, "article": article, "tweet_url": tweet_url})
        time.sleep(3)  # レート制限対策

    print(f"\n🎉 完了: {len([r for r in results if not r.get('skipped')])} 件投稿")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="note 自動収益化パイプライン")
    parser.add_argument("--dry-run", action="store_true", help="投稿せずに内容確認のみ")
    parser.add_argument("--count", type=int, help="生成する記事数（デフォルト: config.topics_per_run）")
    parser.add_argument("--report-only", action="store_true", help="分析レポートのみ表示")
    parser.add_argument("--free", action="store_true", help="無料記事として投稿（時間判定を上書き）")
    parser.add_argument("--paid", action="store_true", help="有料記事として投稿（時間判定を上書き）")
    args = parser.parse_args()

    if args.report_only:
        run_report()
    else:
        forced_price = None
        if args.free:
            forced_price = 0
        elif args.paid:
            forced_price = config.default_price
        run_pipeline(dry_run=args.dry_run, count=args.count, price=forced_price)
