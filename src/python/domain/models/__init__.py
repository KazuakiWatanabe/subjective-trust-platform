"""ドメインモデル一覧。

全モデルをここでインポートし、Alembic の autogenerate が検出できるようにする。
"""

from src.python.domain.models.base import Base
from src.python.domain.models.complaint_inquiry import ComplaintInquiry
from src.python.domain.models.customer import Customer
from src.python.domain.models.feedback import Feedback
from src.python.domain.models.purchase import Purchase
from src.python.domain.models.review_external import ReviewExternal
from src.python.domain.models.staff import Staff
from src.python.domain.models.store import Store
from src.python.domain.models.trust_event import TrustEvent
from src.python.domain.models.trust_score_snapshot import TrustScoreSnapshot
from src.python.domain.models.visit import Visit

__all__ = [
    "Base",
    "ComplaintInquiry",
    "Customer",
    "Feedback",
    "Purchase",
    "ReviewExternal",
    "Staff",
    "Store",
    "TrustEvent",
    "TrustScoreSnapshot",
    "Visit",
]
