"""メインパイプライン: 分析 → テーマ選定 → 記事生成 → 投稿 → SNS宣伝。"""
import time
import argparse
from note_client import NoteClient
from generator import suggest_topics, generate_article, generate_tweet
from twitter_client import tweet
from analytics import run_report
from config import config


def run_pipeline(dry_run: bool = False, count: int | None = None):
    note = NoteClient()
    n = count or config.topics_per_run

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
            print(f"  [DRY RUN] 投稿スキップ")
            print(f"  無料パート ({len(free_body)}文字) + 有料パート ({len(paid_body)}文字)")
            results.append({"topic": topic, "skipped": True})
            continue

        print(f"  📤 note へ投稿中...")
        article = note.post_article(
            title=topic["title"],
            body=full_body,
            price=topic.get("price", config.default_price),
            free_body=free_body,
            magazine_id=config.magazine_id,
            hashtags=topic.get("hashtags", []),
        )
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
    args = parser.parse_args()

    if args.report_only:
        run_report()
    else:
        run_pipeline(dry_run=args.dry_run, count=args.count)
