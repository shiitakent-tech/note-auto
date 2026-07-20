"""Claude を使った記事生成 + テーマ選定。"""
from __future__ import annotations

import json
import re
import anthropic
from config import config

client = anthropic.Anthropic(api_key=config.anthropic_api_key)

TOPIC_PROMPT = """
あなたはnote.comでAI活用ジャンルの人気クリエイターです。
ChatGPTだけでなく Claude（Anthropic社のAI）も得意分野として発信しています。
AIに興味がある人全般（初心者〜上級者）に向けて、お金を払ってでも読みたくなる記事テーマを{n}個提案してください。

過去データ（ビュー数・いいね数など）:
{stats_json}

【重要】以下は既に公開済みのタイトル一覧です。これらと同じ・似たテーマは絶対に選ばないでください:
{existing_titles}

テーマ選定の基準:
- 「これ知りたかった！」と思わせる具体的なノウハウや気づきがあること
- 読んだ後に生活・仕事・収入が実際に変わる実践的な内容
- タイトルを見た瞬間にクリックしたくなる強いフック
- 上記の既存タイトルと内容・切り口が被らないこと（類似テーマも不可）
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

ARTICLE_FROM_SOURCE_PROMPT = """
あなたはAI活用ジャンルで人気のnoteクリエイターです。
以下は、ある書籍・資料を NotebookLM で読み込み、「要点」と「出典」を抽出したメモです。
このメモを“根拠”として、読者が「お金を払う価値があった」と感じる note 記事を1本書いてください。

【素材メモ（NotebookLM抽出：要点＋出典）】
{source}
{angle_block}
執筆の原則:
- 記事の主張は、上の素材メモの要点に必ず根拠を置く（メモに無い事実・数字を捏造しない）
- 重要な主張には、素材内の出典（章・節・ページ・該当箇所）を「（第3章より）」のように自然に織り込む
- 「ここは書籍/資料の主張」「ここからは私の解釈・実体験」を読者が区別できるように書く
- 抽象論で終わらせず、読者が今日から試せる手順・プロンプト・チェックリストを必ず入れる
- 書き手の体験・気づき・失敗談を交え、人間味のある文章にする（「私も最初は〜」など）
- 素材メモに書かれていない論点が必要なら、推測だと分かる書き方にする（断定しない）

構成要件:
- 全文 2500〜4000文字、Markdown（見出し ##、リスト、太字などを活用）
- 無料公開パート（最初の{free_chars}文字程度）:
  - 読者の悩みに共感する導入 → この記事で何が得られるかの提示 → 続きを読みたくなる引き
- 有料パート:
  - 素材の核心ノウハウ（出典つき）／具体的な手順・テンプレ／よくある誤解と対処／まとめと次の一歩

出力は、次の“ファイル形式そのまま”で返してください（前後の説明・コードフェンスは一切不要）:
---
title: 読んだ瞬間にクリックしたくなるタイトル
hashtags: ["タグ1", "タグ2", "タグ3"]
price: {price}
---
（無料パート本文）

---有料ここから---

（有料パート本文）
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


def _ask(prompt: str, prefill: str | None = None, max_tokens: int = 4096,
         model: str | None = None) -> str:
    messages = [{"role": "user", "content": prompt}]
    if prefill:
        # assistant側を途中まで埋めておくと、その続きから書かせられる（Anthropicのprefill）
        messages.append({"role": "assistant", "content": prefill})
    msg = client.messages.create(
        model=model or config.claude_model,
        max_tokens=max_tokens,
        messages=messages,
    )
    text = msg.content[0].text.strip()
    return (prefill + text) if prefill else text


def _extract_json_array(raw: str):
    """LLM出力からJSON配列を頑健に取り出す。取り出せなければ None。"""
    # コードフェンス（```json など）を除去
    text = re.sub(r"```(?:json)?", "", raw).strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end <= start:
        return None
    chunk = text[start:end]
    # 末尾カンマ（ ,] や ,} ）を除去してから解析
    chunk = re.sub(r",\s*([\]}])", r"\1", chunk)
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        return None


def suggest_topics(stats: list, n: int = 3) -> list:
    stats_json = json.dumps(stats, ensure_ascii=False, indent=2)
    existing = [f"- {s['title']}" for s in stats if s.get("title")]
    existing_titles = "\n".join(existing) if existing else "（まだ記事なし）"
    for _ in range(3):
        raw = _ask(TOPIC_PROMPT.format(n=n, stats_json=stats_json, existing_titles=existing_titles),
                   model=config.claude_model_cheap)
        topics = _extract_json_array(raw)
        if topics:
            return topics
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


def generate_article_from_source(source_text: str, price: int | None = None,
                                 angle: str | None = None) -> str:
    """NotebookLM等の素材メモから、scheduled/形式の記事ファイル全文（フロントマター付き）を生成して返す。

    angle: 記事の切り口・編集方針（例「本の原則をAI活用に結びつける」）。Noneなら素直に記事化。
    """
    p = config.default_price if price is None else price
    angle_block = ""
    if angle:
        angle_block = (
            "\n【記事の方向性（最優先で従う編集方針）】\n"
            f"{angle.strip()}\n"
            "※ ただし本/資料の核心原則は、素材メモの出典つきで正確に扱うこと。\n"
        )
    raw = _ask(
        ARTICLE_FROM_SOURCE_PROMPT.format(
            source=source_text.strip(),
            angle_block=angle_block,
            free_chars=config.free_part_chars,
            price=p,
        ),
        max_tokens=8192,         # フロントマター＋全文（〜4000字）が切れないよう余裕を持たせる
    )
    # 前置き文や“全体を囲う”コードフェンスを除き、フロントマター（先頭の ---）から始める。
    # 本文中の ``` プロンプト枠は残す（消すと note でコピペ枠にならない）。
    text = raw.strip()
    idx = text.find("---")
    if idx > 0:
        text = text[idx:]
    text = text.strip()
    if text.endswith("```"):          # 全体を ``` で囲ってきた場合の“閉じ”だけ除去
        text = text[:-3].rstrip()
    return text


def generate_tweet(title: str, url: str, hashtags: list) -> str:
    return _ask(X_PROMPT.format(title=title, url=url, hashtags=" ".join(f"#{h}" for h in hashtags)),
                model=config.claude_model_cheap)
