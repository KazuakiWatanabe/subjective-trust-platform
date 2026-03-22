"""PII マスキングモジュール。

外部レビュー向けのマスキング関数を提供する。
既存の pipeline.py の mask_pii と併用する。

Note:
    Phase 1 では正規表現ベース。Phase 2 以降で LLM ベースの精度向上を図る。
"""

import re

# スタッフ氏名パターン（ひらがな・カタカナ + さん/様）
_STAFF_NAME_PATTERN = re.compile(
    r"[ぁ-ん]{1,4}[さ様](?:ん)?|[ァ-ヶ]{2,6}[さ様](?:ん)?",
)

# 電話番号パターン
_PHONE_PATTERN = re.compile(r"0\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4}")

# メールアドレスパターン
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")


def mask_review_text(text: str) -> str:
    """外部レビューテキストの PII をマスキングする。

    Args:
        text: マスキング対象テキスト

    Returns:
        PII がマスクされたテキスト

    Note:
        スタッフ氏名パターン → 「スタッフ」に置換
        電話番号パターン → 「[電話番号]」に置換
        メールアドレスパターン → 「[メール]」に置換
    """
    result = _EMAIL_PATTERN.sub("[メール]", text)
    result = _PHONE_PATTERN.sub("[電話番号]", result)
    result = _STAFF_NAME_PATTERN.sub("スタッフ", result)
    return result


# reviewer_name は保存しない方針。保存時に固定値を使用する
ANONYMOUS_REVIEWER_NAME: str = "（匿名）"
