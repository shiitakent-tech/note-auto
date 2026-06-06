"""Claude を使った記事生成 + テーマ選定。"""
import json
import anthropic
from config import config

client = anthropic.Anthropic(api_key=config.anthropic_api_key)

TOPIC_PROMPT = """
あなたはnote.comで収益を最大化するコンテンツストラテジストです。
以下の過去記事パフォーマンスデータを分析し、次に書くべき記事テーマを{n}個提案してください。

過去データ:
{stats_json}

制約:
- 有料記事（300〜500円）として成立する深さ・専門性があること
- SEO的に検索需要があること
- 既存記事と重複しないこと

JSON配列で返答してください（他のテキスト不要）:
[
  {{
    "title": "記事タイトル",
    "hashtags": ["タグ1", "タグ2"],
    "price": 300,
    "summary": "記事の概要（2〜3文）"
  }}
]
"""

ARTICLE_PROMPT = """
あなたはnote.comで月20万円以上稼ぐプロライターです。
以下のテーマで高品質な有料記事を書いてください。

タイトル: {title}
概要: {summary}
ハッシュタグ: {hashtags}

要件:
- 全文: 2000〜3000文字
- 無料公開パート（最初の{free_chars}文字程度）: 読者の興味を引く導入 + 記事の価値を伝える
- 有料パート: 具体的な手法・事例・データ・チェックリストなど実践的内容
- 「---有料ここから---」という区切り行を必ず入れること
- Markdownで書くこと（見出し##、リスト、太字など活用）

記事本文のみ出力（前後の説明不要）:
"""

X_PROMPT = """
以下のnote記事をX(Twitter)で宣伝する投稿文を作成してください。

タイトル: {title}
URL: {url}
ハッシュタグ: {hashtags}

要件:
- 140文字以内（URLの22文字分を引いた118文字以内）
- 興味を引くキャッチコピー
- ハッシュタグ2〜3個を末尾に

投稿文のみ出力:
"""


def _ask(prompt: str) -> str:
    msg = client.messages.create(
        model=config.claude_model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def suggest_topics(stats: list[dict], n: int = 3) -> list[dict]:
    stats_json = json.dumps(stats, ensure_ascii=False, indent=2)
    raw = _ask(TOPIC_PROMPT.format(n=n, stats_json=stats_json))
    # JSON部分だけ抽出
    start = raw.find("[")
    end = raw.rfind("]") + 1
    return json.loads(raw[start:end])


def generate_article(topic: dict) -> tuple[str, str]:
    """(free_body, paid_body) を返す。"""
    raw = _ask(ARTICLE_PROMPT.format(
        title=topic["title"],
        summary=topic["summary"],
        hashtags=", ".join(topic["hashtags"]),
        free_chars=config.free_part_chars,
    ))
    separator = "---有料ここから---"
    if separator in raw:
        parts = raw.split(separator, 1)
        return parts[0].strip(), parts[1].strip()
    # セパレータがない場合は先頭を無料パートに
    cut = min(config.free_part_chars, len(raw) // 3)
    return raw[:cut].strip(), raw[cut:].strip()


def generate_tweet(title: str, url: str, hashtags: list[str]) -> str:
    return _ask(X_PROMPT.format(title=title, url=url, hashtags=" ".join(f"#{h}" for h in hashtags)))
