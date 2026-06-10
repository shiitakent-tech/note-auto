"""Claude を使った記事生成 + テーマ選定。"""
import json
import anthropic
from config import config

client = anthropic.Anthropic(api_key=config.anthropic_api_key)

TOPIC_PROMPT = """
あなたはnote.comでAI活用ジャンルの人気クリエイターです。
ChatGPTだけでなく Claude（Anthropic社のAI）も得意分野として発信しています。
AIに興味がある人全般（初心者〜上級者）に向けて、お金を払ってでも読みたくなる記事テーマを{n}個提案してください。

過去データ:
{stats_json}

テーマ選定の基準:
- 「これ知りたかった！」と思わせる具体的なノウハウや気づきがあること
- 読んだ後に生活・仕事・収入が実際に変わる実践的な内容
- タイトルを見た瞬間にクリックしたくなる強いフック
- 既存記事と重複しないこと
- 有料（300〜500円）として納得感がある深さ・専門性
- 扱うAIツールは ChatGPT と Claude をバランスよく。特に Claude ならではの強み
  （長文読解・自然な日本語の文章力・コード・丁寧な対話など）を活かしたテーマも積極的に入れる

良いテーマの例:
- 「Claudeに〇〇させたら、ChatGPTより△△が良かった比較実録」
- 「文章を書くなら Claude 一択だった理由と、実際のプロンプト集」
- 「ChatGPTに〇〇させたら△△時間が▲▲分になった実録」
- 「ChatGPTとClaude、結局どっちを使うべき？目的別の使い分け完全ガイド」
- 「AIを使って月〇万円副収入を作った具体的な手順書」

JSON配列で返答してください（他のテキスト不要）:
[
  {{
    "title": "記事タイトル",
    "hashtags": ["タグ1", "タグ2"],
    "price": 300,
    "summary": "記事の概要（2〜3文）。読んだ後に何が得られるかを明確に。"
  }}
]
"""

ARTICLE_PROMPT = """
あなたはAI活用ジャンルで人気のnoteクリエイターで、ChatGPTとClaude（Anthropic社のAI）の
両方に精通しています。テーマがClaude関連なら、Claudeならではの強み（自然な日本語の文章力、
長文の読解・要約、丁寧な対話、コードの正確さなど）を具体的に伝えてください。
以下のテーマで、読者が「これはお金を払う価値があった」と感じる記事を書いてください。

タイトル: {title}
概要: {summary}
ハッシュタグ: {hashtags}

執筆の原則:
- 「で、結局どうすればいいの？」に必ず答える
- 抽象論ではなく、コピペして使えるプロンプト・手順・テンプレートを入れる
- 書き手の実体験・失敗談・気づきを交える（「私も最初は〜」など）
- 読者が読み終えた後、すぐに行動できる状態にする

構成要件:
- 全文: 2500〜4000文字
- 無料公開パート（最初の{free_chars}文字程度）:
  - 読者の悩みや状況に共感する導入
  - 「この記事を読むと〇〇ができるようになる」という価値の提示
  - 読者が「続きを読みたい！」と感じる引き
- 有料パート:
  - 具体的な手順・プロンプト全文・テンプレート
  - よくある失敗とその対処法
  - 応用テクニックや上級者向けTips
  - まとめ＋次のアクション
- 「---有料ここから---」という区切り行を必ず入れること
- Markdownで書くこと（見出し##、リスト、太字、コードブロックなど活用）

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


def suggest_topics(stats: list, n: int = 3) -> list:
    stats_json = json.dumps(stats, ensure_ascii=False, indent=2)
    for attempt in range(3):
        raw = _ask(TOPIC_PROMPT.format(n=n, stats_json=stats_json))
        start = raw.find("[")
        end = raw.rfind("]") + 1
        if start == -1 or end == 0:
            continue
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            continue
    raise RuntimeError("テーマ提案のJSON解析に3回失敗しました")


def generate_article(topic: dict) -> tuple:
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


def generate_tweet(title: str, url: str, hashtags: list) -> str:
    return _ask(X_PROMPT.format(title=title, url=url, hashtags=" ".join(f"#{h}" for h in hashtags)))
