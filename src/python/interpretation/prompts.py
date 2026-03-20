"""AI 解釈プロンプト定義。

設計書 §3.3 に基づく AI 解釈パイプライン用プロンプトテンプレート。
プロンプトは PROMPT_VERSION 定数でバージョン管理する。

Note:
    プロンプト改訂時は PROMPT_VERSION を更新し、変更履歴をコメントで残すこと。
    分類精度の目標: 信頼次元の正答率 85% 以上、感情分類の正答率 90% 以上。
    週次で 100 件のサンプリング検証を行い、目標未達時にプロンプトを改訂する。
"""

# プロンプトバージョン管理
# 改訂時はバージョンを更新し、変更内容をコメントで記録すること
# v1.0.0: 初版 — 5次元分類・感情分類・主観手がかり抽出
PROMPT_VERSION: str = "1.0.0"

# 出力スキーマの JSON 説明（プロンプトに埋め込む）
_OUTPUT_SCHEMA_DESCRIPTION: str = """\
以下の JSON スキーマに厳密に従って出力してください。JSON 以外のテキストは含めないでください。

{
  "trust_dimension": "service | product | proposal | operation | story のいずれか1つ",
  "sentiment": "positive | negative | neutral のいずれか1つ",
  "severity": "1（軽微）| 2（中程度）| 3（重大）のいずれか",
  "theme_tags": ["該当するテーマタグを配列で（例: 押し売り感, 説明不足, 丁寧な接客）"],
  "summary": "テキストの内容を1文で要約",
  "interpretation": "顧客がなぜそう感じたと推定されるかを1文で説明",
  "subjective_hints": {
    "trait_signal": "長期的な価値観・選好の手がかり（例: 品質重視の傾向）、なければ null",
    "state_signal": "来店時の短期的状態の手がかり（例: ギフト選びで慎重）、なければ null",
    "meta_signal": "過去体験への違和感・修正の手がかり（例: 前回の欠品不満が再燃）、なければ null"
  },
  "confidence": "0.0〜1.0 の数値。分類の確信度"
}"""

# 信頼次元の説明（プロンプトに埋め込む）
_DIMENSION_DESCRIPTION: str = """\
■ 信頼の5次元の定義:
- service（接客信頼）: 安心して相談でき、不快な思いをしないか
- product（商品信頼）: 期待した品質・価格納得感があるか
- proposal（提案信頼）: 自分に合った提案がされているか
- operation（運営信頼）: 在庫・案内・受取に齟齬がないか
- story（物語信頼）: ブランドらしさと一貫性が保たれているか"""

# システムプロンプト
_SYSTEM_PROMPT: str = f"""\
あなたは実店舗のブランド信頼を分析する専門家です。
顧客の自由記述テキストを読み、ブランド信頼の観点で構造的に解釈してください。

{_DIMENSION_DESCRIPTION}

■ 解釈のルール:
1. テキストが最も強く関連する信頼次元を1つ選んでください
2. sentiment は顧客の感情極性（positive/negative/neutral）を判定してください
3. severity は信頼への影響度を 1（軽微）〜 3（重大）で評価してください
4. interpretation には「なぜそう感じたか」の仮説を必ず含めてください
   - 単なる分類結果の繰り返しではなく、改善の手がかりとなる解釈を記述してください
5. subjective_hints には顧客の Trait（長期的価値観）・State（来店時状態）・Meta（過去体験への違和感）の手がかりがあれば抽出してください
6. confidence は分類の確信度を 0.0〜1.0 で自己評価してください
   - テキストが曖昧・短すぎる場合は低い値を付けてください

{_OUTPUT_SCHEMA_DESCRIPTION}"""


def build_interpretation_prompt(text: str) -> str:
    """AI 解釈用のユーザープロンプトを生成する。

    Args:
        text: 解釈対象の自由記述テキスト。
              個人識別情報はマスキング済みであること。

    Returns:
        AI に送信するプロンプト文字列（システムプロンプト + ユーザーテキスト）
    """
    return f"""{_SYSTEM_PROMPT}

--- 以下が解釈対象テキストです ---

{text}

--- JSON のみで回答してください ---"""


def get_system_prompt() -> str:
    """システムプロンプトを返す。

    Returns:
        AI API の system パラメータに渡すプロンプト文字列
    """
    return _SYSTEM_PROMPT
