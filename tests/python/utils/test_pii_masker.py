"""PII マスキングのユニットテスト。

対象: src/python/utils/pii_masker.py
"""

from src.python.utils.pii_masker import mask_review_text


class TestMaskReviewText:
    """mask_review_text のテスト。"""

    def test_スタッフ氏名がマスキングされる(self) -> None:
        text = "たなかさんの対応がとても丁寧でした"
        result = mask_review_text(text)
        assert "たなかさん" not in result
        assert "スタッフ" in result

    def test_カタカナ氏名がマスキングされる(self) -> None:
        text = "タナカ様の説明がわかりやすかった"
        result = mask_review_text(text)
        assert "タナカ様" not in result
        assert "スタッフ" in result

    def test_電話番号がマスキングされる(self) -> None:
        text = "連絡先は03-1234-5678です"
        result = mask_review_text(text)
        assert "03-1234-5678" not in result
        assert "[電話番号]" in result

    def test_両方含まれるケース(self) -> None:
        text = "やまださんに電話 090-1111-2222 で連絡しました"
        result = mask_review_text(text)
        assert "やまださん" not in result
        assert "090-1111-2222" not in result
        assert "スタッフ" in result
        assert "[電話番号]" in result

    def test_マスキング対象がないケース(self) -> None:
        text = "商品の品質がとても良かったです"
        result = mask_review_text(text)
        assert result == text
