"""外部レビュー専用 AI 解釈プロンプト。

Google 口コミ等の外部レビュー解釈に使用する。
1 テキスト内に複数次元が混在するケースに対応する mentions 配列を出力する。

Note:
    既存の interpretation/prompts.py は単一接点向け。
    外部レビューは複数来店体験の総括になりやすいため専用プロンプトを使用する。
"""

PROMPT_VERSION: str = "review-1.0.0"

EXTERNAL_REVIEW_PROMPT_TEMPLATE: str = """\
あなたはブランド信頼の分析専門家です。
以下の実店舗に対するGoogle口コミを分析し、指定のJSON形式で出力してください。

## 分析対象レビュー

評価点: {rating}点（5点満点）
投稿日: {review_date}
本文:
{review_text}

## 分析指示

Google口コミは複数の体験をまとめて書かれる場合があります。
本文全体を読み、以下の5つの信頼次元のうち**言及されているすべての次元**を特定し、
それぞれについて感情・重要度・解釈を出力してください。

### 信頼次元の定義
- product  : 商品の品質・価格納得感・期待一致
- service  : 接客の安心感・丁寧さ・不快感の有無
- proposal : 提案の的確さ・自分に合っているか
- operation: 在庫案内・受取・価格表示の正確さ
- story    : ブランドらしさ・世界観の一貫性

### 注意事項
- 評価点（星）と本文の感情が一致しない場合は本文を優先してください
- 競合他社との比較が含まれる場合は、本店舗への評価のみを対象にしてください
- 推測できない次元は出力しないでください

## 出力形式（JSONのみ。前置き・後置き不要）

{{
  "mentions": [
    {{
      "trust_dimension": "service | product | proposal | operation | story",
      "sentiment": "positive | negative | neutral",
      "severity": 1 | 2 | 3,
      "theme_tags": ["タグ1", "タグ2"],
      "summary": "この次元に関する1文の要約",
      "interpretation": "なぜそう感じたと推定されるかの1文解釈",
      "confidence": 0.0〜1.0
    }}
  ],
  "subjective_hints": {{
    "trait_signal": "長期的な価値観・選好の手がかり（なければnull）",
    "state_signal": "来店時の状態・目的の手がかり（なければnull）",
    "meta_signal": "過去体験への言及・繰り返しパターン（なければnull）"
  }},
  "overall_sentiment": "positive | negative | neutral | mixed",
  "review_type": "single_visit | multi_visit | comparison | unknown",
  "contains_competitor_mention": true | false
}}"""


def build_review_prompt(
    rating: int,
    review_date: str,
    review_text: str,
) -> str:
    """外部レビュー解釈用プロンプトを生成する。

    Args:
        rating: 評価点（1〜5）
        review_date: 投稿日（YYYY-MM-DD）
        review_text: レビュー本文（PII マスキング済み）

    Returns:
        AI に送信するプロンプト文字列
    """
    return EXTERNAL_REVIEW_PROMPT_TEMPLATE.format(
        rating=rating,
        review_date=review_date,
        review_text=review_text,
    )
