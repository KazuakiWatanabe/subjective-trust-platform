"""デモ用初期データ投入スクリプト。

Store 3 件、Staff 6 件、Visit 15 件、Feedback 9 件、ReviewExternal 6 件、
TrustScoreSnapshot 3 件を投入する。

Usage:
    docker compose exec api python scripts/seed_demo.py
"""

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# パスを通す
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.python.domain.models import (  # noqa: E402
    Base,
    Feedback,
    ReviewExternal,
    Staff,
    Store,
    TrustEvent,
    TrustScoreSnapshot,
    Visit,
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://trust_user:trust_pass@db:5432/trust_platform",
)

# --- 固定 UUID（デモで再利用しやすいように） ---

STORE_IDS = {
    "shibuya": uuid.UUID("10000000-0000-0000-0000-000000000001"),
    "shinjuku": uuid.UUID("10000000-0000-0000-0000-000000000002"),
    "ginza": uuid.UUID("10000000-0000-0000-0000-000000000003"),
}

STAFF_IDS = {
    "shibuya_1": uuid.UUID("20000000-0000-0000-0000-000000000001"),
    "shibuya_2": uuid.UUID("20000000-0000-0000-0000-000000000002"),
    "shinjuku_1": uuid.UUID("20000000-0000-0000-0000-000000000003"),
    "shinjuku_2": uuid.UUID("20000000-0000-0000-0000-000000000004"),
    "ginza_1": uuid.UUID("20000000-0000-0000-0000-000000000005"),
    "ginza_2": uuid.UUID("20000000-0000-0000-0000-000000000006"),
}

now = datetime.now(timezone.utc)


def _ts(days_ago: int = 0, hours: int = 14) -> datetime:
    """days_ago 日前の指定時刻を返す。"""
    return (now - timedelta(days=days_ago)).replace(hour=hours, minute=0, second=0)


async def seed(session: AsyncSession) -> None:
    """デモデータを投入する。"""

    # --- Store ---
    stores = [
        Store(store_id=STORE_IDS["shibuya"], store_name="渋谷店", area="東京", format_type="直営", open_date=date(2025, 4, 1), status="active"),
        Store(store_id=STORE_IDS["shinjuku"], store_name="新宿店", area="東京", format_type="直営", open_date=date(2025, 6, 1), status="active"),
        Store(store_id=STORE_IDS["ginza"], store_name="銀座店", area="東京", format_type="直営", open_date=date(2025, 9, 1), status="active"),
    ]
    session.add_all(stores)
    await session.flush()

    # --- Staff ---
    staffs = [
        Staff(staff_id=STAFF_IDS["shibuya_1"], store_id=STORE_IDS["shibuya"], staff_name="田中花子", role="店長", status="active"),
        Staff(staff_id=STAFF_IDS["shibuya_2"], store_id=STORE_IDS["shibuya"], staff_name="佐藤太郎", role="スタッフ", status="active"),
        Staff(staff_id=STAFF_IDS["shinjuku_1"], store_id=STORE_IDS["shinjuku"], staff_name="鈴木一郎", role="店長", status="active"),
        Staff(staff_id=STAFF_IDS["shinjuku_2"], store_id=STORE_IDS["shinjuku"], staff_name="高橋美咲", role="スタッフ", status="active"),
        Staff(staff_id=STAFF_IDS["ginza_1"], store_id=STORE_IDS["ginza"], staff_name="伊藤健太", role="店長", status="active"),
        Staff(staff_id=STAFF_IDS["ginza_2"], store_id=STORE_IDS["ginza"], staff_name="渡辺愛", role="スタッフ", status="active"),
    ]
    session.add_all(staffs)
    await session.flush()

    # --- Visit（各店舗5件） ---
    visit_data = [
        # 渋谷店
        (STORE_IDS["shibuya"], STAFF_IDS["shibuya_1"], "purchase", "purchase", 1),
        (STORE_IDS["shibuya"], STAFF_IDS["shibuya_2"], "gift", "purchase", 2),
        (STORE_IDS["shibuya"], STAFF_IDS["shibuya_1"], "browsing", "exit", 3),
        (STORE_IDS["shibuya"], STAFF_IDS["shibuya_2"], "comparison", "considering", 4),
        (STORE_IDS["shibuya"], STAFF_IDS["shibuya_1"], "purchase", "out_of_stock_exit", 5),
        # 新宿店
        (STORE_IDS["shinjuku"], STAFF_IDS["shinjuku_1"], "gift", "purchase", 1),
        (STORE_IDS["shinjuku"], STAFF_IDS["shinjuku_2"], "purchase", "purchase", 2),
        (STORE_IDS["shinjuku"], STAFF_IDS["shinjuku_1"], "browsing", "considering", 3),
        (STORE_IDS["shinjuku"], STAFF_IDS["shinjuku_2"], "repair_inquiry", "exit", 4),
        (STORE_IDS["shinjuku"], STAFF_IDS["shinjuku_1"], "comparison", "purchase", 5),
        # 銀座店
        (STORE_IDS["ginza"], STAFF_IDS["ginza_1"], "purchase", "purchase", 1),
        (STORE_IDS["ginza"], STAFF_IDS["ginza_2"], "gift", "out_of_stock_exit", 2),
        (STORE_IDS["ginza"], STAFF_IDS["ginza_1"], "browsing", "exit", 3),
        (STORE_IDS["ginza"], STAFF_IDS["ginza_2"], "purchase", "purchase", 4),
        (STORE_IDS["ginza"], STAFF_IDS["ginza_1"], "comparison", "considering", 5),
    ]

    visits: list[Visit] = []
    for store_id, staff_id, purpose, result, days_ago in visit_data:
        v = Visit(
            visit_id=uuid.uuid4(),
            store_id=store_id,
            staff_id=staff_id,
            visit_datetime=_ts(days_ago),
            visit_purpose=purpose,
            purchase_flag=(result == "purchase"),
            contact_result=result,
            out_of_stock_flag=(result == "out_of_stock_exit"),
            alternative_proposed=False if result == "out_of_stock_exit" else None,
            anxiety_tags=["price", "competitor"] if result == "exit" else None,
        )
        visits.append(v)
    session.add_all(visits)
    await session.flush()  # Visit を先に書き込んでから Feedback を追加（FK 制約）

    # --- Feedback（各店舗3件 = 先頭3つの Visit に紐づけ） ---
    feedback_data = [
        # (visit_index, score_c, score_i, score_r, free_comment)
        (0, 5, 4, 5, "スタッフの説明がとても分かりやすく、安心して購入できました。"),
        (1, 4, 3, 4, "ギフト用の包装もきれいにしてもらえました。ただ、もう少し選択肢があると嬉しいです。"),
        (2, 2, 2, 1, "店内が混雑していて、スタッフに声をかけづらかった。別の店舗も検討したい。"),
        (5, 5, 5, 5, "素晴らしい接客でした。プレゼント選びの相談に親身に乗ってもらえました。"),
        (6, 3, 4, 3, "商品は良かったのですが、少し押し売り感がありました。"),
        (8, 2, 1, 2, "修理の受付に時間がかかりすぎる。改善してほしい。"),
        (10, 4, 5, 4, "品揃えが豊富で、じっくり選べました。接客も丁寧でした。"),
        (11, 1, 2, 1, "欲しかった商品が在庫切れで、代わりの提案もなかった。非常に残念。"),
        (13, 5, 4, 5, "いつも安心して買い物できます。ブランドの世界観が素敵です。"),
    ]

    for visit_idx, sc, si, sr, comment in feedback_data:
        fb = Feedback(
            feedback_id=uuid.uuid4(),
            visit_id=visits[visit_idx].visit_id,
            score_consultation=sc,
            score_information=si,
            score_revisit=sr,
            free_comment=comment,
            submitted_at=visits[visit_idx].visit_datetime + timedelta(hours=24),
        )
        session.add(fb)

    # --- ReviewExternal（各店舗2件） ---
    reviews = [
        ReviewExternal(review_id=uuid.uuid4(), store_id=STORE_IDS["shibuya"], platform="google", rating=5, review_text="接客が素晴らしい。何度も通いたくなるお店。", posted_at=_ts(2), fetched_at=now),
        ReviewExternal(review_id=uuid.uuid4(), store_id=STORE_IDS["shibuya"], platform="google", rating=3, review_text="商品は良いが、混雑時の対応が雑に感じた。", posted_at=_ts(5), fetched_at=now),
        ReviewExternal(review_id=uuid.uuid4(), store_id=STORE_IDS["shinjuku"], platform="google", rating=4, review_text="ギフト選びで丁寧にアドバイスしてもらえた。", posted_at=_ts(1), fetched_at=now),
        ReviewExternal(review_id=uuid.uuid4(), store_id=STORE_IDS["shinjuku"], platform="google", rating=2, review_text="店員の態度が高圧的。もう行きたくない。", posted_at=_ts(3), fetched_at=now),
        ReviewExternal(review_id=uuid.uuid4(), store_id=STORE_IDS["ginza"], platform="google", rating=5, review_text="さすが銀座店。ブランドの世界観を感じる空間。", posted_at=_ts(2), fetched_at=now),
        ReviewExternal(review_id=uuid.uuid4(), store_id=STORE_IDS["ginza"], platform="google", rating=1, review_text="在庫切れが多すぎる。事前に確認すべきだった。", posted_at=_ts(4), fetched_at=now),
    ]
    session.add_all(reviews)

    # --- TrustScoreSnapshot（各店舗1件） ---
    today = date.today()
    snapshots = [
        TrustScoreSnapshot(
            snapshot_id=uuid.uuid4(), target_type="store", target_id=STORE_IDS["shibuya"],
            snapshot_date=today, product_score=Decimal("55.20"), service_score=Decimal("62.50"),
            proposal_score=Decimal("48.00"), operation_score=Decimal("51.30"), story_score=Decimal("58.80"),
            overall_score=Decimal("55.16"), event_count=25, is_reliable=True,
        ),
        TrustScoreSnapshot(
            snapshot_id=uuid.uuid4(), target_type="store", target_id=STORE_IDS["shinjuku"],
            snapshot_date=today, product_score=Decimal("52.00"), service_score=Decimal("45.30"),
            proposal_score=Decimal("50.10"), operation_score=Decimal("47.50"), story_score=Decimal("53.20"),
            overall_score=Decimal("49.62"), event_count=22, is_reliable=True,
        ),
        TrustScoreSnapshot(
            snapshot_id=uuid.uuid4(), target_type="store", target_id=STORE_IDS["ginza"],
            snapshot_date=today, product_score=Decimal("58.50"), service_score=Decimal("60.00"),
            proposal_score=Decimal("42.00"), operation_score=Decimal("44.80"), story_score=Decimal("65.00"),
            overall_score=Decimal("54.06"), event_count=18, is_reliable=False,
        ),
    ]
    session.add_all(snapshots)

    await session.commit()
    print("デモデータ投入完了:")
    print(f"  Store: {len(stores)} 件")
    print(f"  Staff: {len(staffs)} 件")
    print(f"  Visit: {len(visits)} 件")
    print(f"  Feedback: {len(feedback_data)} 件")
    print(f"  ReviewExternal: {len(reviews)} 件")
    print(f"  TrustScoreSnapshot: {len(snapshots)} 件")


async def main() -> None:
    """メイン実行。"""
    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        # 既存データがあればスキップ
        result = await session.execute(text("SELECT count(*) FROM store"))
        count = result.scalar()
        if count and count > 0:
            print(f"既にデータが存在します（store: {count} 件）。スキップします。")
            return

        await seed(session)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
