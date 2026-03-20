"""ドメインモデルのユニットテスト。

対象: src/python/domain/models/
テスト観点: 設計書 §4.2 の全テーブル定義・制約・インデックスが
            SQLAlchemy モデルに正しく反映されていることを検証する。

Note:
    DB 接続は不要。SQLAlchemy のメタデータを検査してスキーマの正しさを証明する。
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import inspect as sa_inspect

from src.python.domain.models import (
    Base,
    ComplaintInquiry,
    Customer,
    Feedback,
    Purchase,
    ReviewExternal,
    Staff,
    Store,
    TrustEvent,
    TrustScoreSnapshot,
    Visit,
)


class TestAllTablesExist:
    """AC-01: 設計書 §4.2 の全テーブルが定義されている。"""

    # AC-01: 設計書 §4.2 の全テーブルが定義されている
    def test_全テーブルがメタデータに登録されている(self) -> None:
        """Base.metadata に設計書の全テーブルが登録されていることを検証する。"""
        table_names = set(Base.metadata.tables.keys())
        expected = {
            "store",
            "staff",
            "customer",
            "visit",
            "feedback",
            "trust_event",
            "trust_score_snapshot",
            "purchase",
            "complaint_inquiry",
            "review_external",
        }
        assert expected.issubset(table_names), (
            f"不足テーブル: {expected - table_names}"
        )

    # AC-01: 各モデルクラスが正しいテーブル名を持つ
    def test_各モデルのテーブル名が正しい(self) -> None:
        """各モデルクラスの __tablename__ を検証する。"""
        assert Store.__tablename__ == "store"
        assert Staff.__tablename__ == "staff"
        assert Customer.__tablename__ == "customer"
        assert Visit.__tablename__ == "visit"
        assert Feedback.__tablename__ == "feedback"
        assert TrustEvent.__tablename__ == "trust_event"
        assert TrustScoreSnapshot.__tablename__ == "trust_score_snapshot"
        assert Purchase.__tablename__ == "purchase"
        assert ComplaintInquiry.__tablename__ == "complaint_inquiry"
        assert ReviewExternal.__tablename__ == "review_external"


class TestTrustEventIndex:
    """AC-02: TrustEvent のインデックス検証。"""

    # AC-02: TrustEvent に (store_id, trust_dimension, detected_at) の複合インデックスがある
    def test_複合インデックスが定義されている(self) -> None:
        """idx_trust_event_store_dim_date が正しいカラムで定義されている。"""
        table = TrustEvent.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "idx_trust_event_store_dim_date" in index_names

    # AC-02: インデックスのカラム構成が正しい
    def test_複合インデックスのカラムが正しい(self) -> None:
        """インデックスのカラムが (store_id, trust_dimension, detected_at) である。"""
        table = TrustEvent.__table__
        target_idx = None
        for idx in table.indexes:
            if idx.name == "idx_trust_event_store_dim_date":
                target_idx = idx
                break
        assert target_idx is not None
        col_names = [col.name for col in target_idx.columns]
        assert col_names == ["store_id", "trust_dimension", "detected_at"]


class TestTrustScoreSnapshotConstraint:
    """AC-03: TrustScoreSnapshot のユニーク制約検証。"""

    # AC-03: TrustScoreSnapshot に (target_type, target_id, snapshot_date) のユニーク制約がある
    def test_ユニーク制約が定義されている(self) -> None:
        """uq_trust_score_snapshot が正しいカラムで定義されている。"""
        table = TrustScoreSnapshot.__table__
        unique_constraints = [
            c
            for c in table.constraints
            if hasattr(c, "columns") and getattr(c, "name", None) == "uq_trust_score_snapshot"
        ]
        assert len(unique_constraints) == 1
        col_names = [col.name for col in unique_constraints[0].columns]
        assert set(col_names) == {"target_type", "target_id", "snapshot_date"}


class TestFeedbackConstraints:
    """Feedback の制約検証。"""

    # AC-01: Feedback.visit_id の UNIQUE 制約（1来店1回答）
    def test_visit_idにユニーク制約がある(self) -> None:
        """visit_id カラムに unique=True が設定されている。"""
        table = Feedback.__table__
        visit_id_col = table.c.visit_id
        assert visit_id_col.unique is True

    # AC-01: score カラムの CHECK 制約（1〜5）
    def test_scoreカラムのCHECK制約が定義されている(self) -> None:
        """score_consultation/information/revisit に CHECK 1-5 が設定されている。"""
        table = Feedback.__table__
        check_names = {
            c.name
            for c in table.constraints
            if c.__class__.__name__ == "CheckConstraint"
        }
        assert "ck_feedback_score_consultation_range" in check_names
        assert "ck_feedback_score_information_range" in check_names
        assert "ck_feedback_score_revisit_range" in check_names


class TestTrustEventColumns:
    """TrustEvent のカラム定義検証。"""

    # AC-01: TrustEvent が設計書のカラムをすべて持つ
    def test_設計書の全カラムが定義されている(self) -> None:
        """TrustEvent に設計書 §4.2 の全カラムが存在する。"""
        table = TrustEvent.__table__
        col_names = {col.name for col in table.columns}
        expected = {
            "trust_event_id",
            "store_id",
            "source_type",
            "source_id",
            "trust_dimension",
            "sentiment",
            "severity",
            "theme_tags",
            "generated_summary",
            "interpretation",
            "trait_signal",
            "state_signal",
            "meta_signal",
            "confidence",
            "needs_review",
            "reviewed_flag",
            "generated_by",
            "detected_at",
        }
        assert expected.issubset(col_names), (
            f"不足カラム: {expected - col_names}"
        )

    # AC-01: severity の CHECK 制約
    def test_severityのCHECK制約が定義されている(self) -> None:
        """severity に CHECK 1-3 が設定されている。"""
        table = TrustEvent.__table__
        check_names = {
            c.name
            for c in table.constraints
            if c.__class__.__name__ == "CheckConstraint"
        }
        assert "ck_trust_event_severity_range" in check_names


class TestModelInstantiation:
    """モデルのインスタンス生成テスト（ORM マッピングの正常性確認）。"""

    # AC-01: Store モデルが正常にインスタンス化できる
    def test_Storeインスタンスが生成できる(self) -> None:
        """Store モデルの基本属性が設定される。"""
        store = Store(
            store_id=uuid.uuid4(),
            store_name="渋谷店",
            area="東京",
            format_type="直営",
            status="active",
        )
        assert store.store_name == "渋谷店"
        assert store.status == "active"

    # AC-01: TrustEvent モデルが正常にインスタンス化できる
    def test_TrustEventインスタンスが生成できる(self) -> None:
        """TrustEvent モデルの基本属性が設定される。"""
        now = datetime.now(timezone.utc)
        event = TrustEvent(
            trust_event_id=uuid.uuid4(),
            store_id=uuid.uuid4(),
            source_type="feedback",
            source_id=uuid.uuid4(),
            trust_dimension="service",
            sentiment="negative",
            severity=2,
            confidence=0.85,
            needs_review=False,
            reviewed_flag=False,
            generated_by="ai",
            detected_at=now,
        )
        assert event.trust_dimension == "service"
        assert event.generated_by == "ai"
