"""パフォーマンス分析 — 収益レポートをコンソール出力 + JSON保存。"""
import json
import os
from datetime import datetime
from note_client import NoteClient


HISTORY_FILE = "analytics_history.jsonl"


def run_report() -> dict:
    client = NoteClient()
    stats = client.get_stats(limit=50)

    total_views = sum(s["views"] for s in stats)
    total_sales = sum(s["sales"] for s in stats)
    paid = [s for s in stats if s["price"] > 0]
    revenue_estimate = sum(s["sales"] * s["price"] for s in paid)

    report = {
        "timestamp": datetime.now().isoformat(),
        "total_articles": len(stats),
        "total_views": total_views,
        "total_sales": total_sales,
        "revenue_estimate_jpy": revenue_estimate,
        "top_by_views": sorted(stats, key=lambda x: x["views"], reverse=True)[:5],
        "top_by_sales": sorted(paid, key=lambda x: x["sales"], reverse=True)[:5],
    }

    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False) + "\n")

    print(f"\n=== note 収益レポート {report['timestamp'][:10]} ===")
    print(f"記事数: {report['total_articles']}  総ビュー: {total_views}  推定収益: ¥{revenue_estimate:,}")
    print("\n[ビュー上位5]")
    for a in report["top_by_views"]:
        print(f"  {a['views']:>6} views  {a['title'][:40]}")
    print("\n[売上上位5]")
    for a in report["top_by_sales"]:
        print(f"  {a['sales']:>4} 件  ¥{a['price']}  {a['title'][:40]}")

    return report


if __name__ == "__main__":
    run_report()
