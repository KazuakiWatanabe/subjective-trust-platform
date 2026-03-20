"""来店（Visit）API スキーマ。

設計書 §5.1 に基づく接客タグ入力のリクエスト・レスポンスモデル。

Note:
    visit_purpose は State 情報として扱う。
    contact_result が欠品離脱の場合のみ alternative_proposed / backorder_offered を受け付ける。
    contact_result が離脱の場合のみ anxiety_tags を受け付ける。
"""
# TODO(phase2): C# 移管予定 — REST API は ASP.NET Core Minimal API に移行する

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class VisitCreateRequest(BaseModel):
    """POST /visits リクエストボディ。

    Args:
        store_id: 店舗 ID（必須）
        visit_purpose: 来店目的（必須）
        contact_result: 接客結果（必須）
        staff_id: 接客担当スタッフ ID（任意）
        customer_id: 顧客 ID（任意。匿名来店は省略）
        alternative_proposed: 代替提案フラグ（欠品離脱時のみ）
        backorder_offered: 取り寄せ案内フラグ（欠品離脱時のみ）
        anxiety_tags: 不安点タグ（離脱時のみ、複数選択）
        next_visit_likelihood: 次回来店見込み（任意）
        staff_note: 特記メモ（任意）
    """

    store_id: uuid.UUID
    visit_purpose: Literal[
        "purchase", "browsing", "comparison", "gift", "repair_inquiry"
    ]
    contact_result: Literal[
        "purchase", "considering", "exit", "out_of_stock_exit"
    ]
    staff_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    alternative_proposed: bool | None = None
    backorder_offered: bool | None = None
    anxiety_tags: list[
        Literal["price", "size_spec", "material_quality", "use_case", "competitor"]
    ] | None = None
    next_visit_likelihood: Literal["high", "medium", "low"] | None = None
    staff_note: str | None = None

    @model_validator(mode="after")
    def validate_conditional_fields(self) -> "VisitCreateRequest":
        """条件付きフィールドのバリデーション。

        Raises:
            ValueError: 欠品離脱以外で alternative_proposed が設定された場合
            ValueError: 離脱以外で anxiety_tags が設定された場合
        """
        # 欠品離脱の場合のみ代替提案フラグを受け付ける
        if self.contact_result != "out_of_stock_exit":
            if self.alternative_proposed is not None:
                raise ValueError(
                    "alternative_proposed は contact_result='out_of_stock_exit' の場合のみ指定可能"
                )
            if self.backorder_offered is not None:
                raise ValueError(
                    "backorder_offered は contact_result='out_of_stock_exit' の場合のみ指定可能"
                )

        # 離脱の場合のみ不安点タグを受け付ける
        if self.contact_result != "exit":
            if self.anxiety_tags is not None and len(self.anxiety_tags) > 0:
                raise ValueError(
                    "anxiety_tags は contact_result='exit' の場合のみ指定可能"
                )

        return self


class VisitResponse(BaseModel):
    """POST /visits レスポンスボディ。"""

    visit_id: uuid.UUID
    store_id: uuid.UUID
    visit_purpose: str
    contact_result: str
    visit_datetime: datetime
    message: str = "来店記録が作成されました"
