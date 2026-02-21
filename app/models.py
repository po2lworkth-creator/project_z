from dataclasses import dataclass
from datetime import datetime
from typing import Optional

# Статусы заявки/роли продавца
SELLER_STATUS_NONE = "none"
SELLER_STATUS_APPLIED = "applied"
SELLER_STATUS_SELLER = "seller"
SELLER_STATUS_REJECTED = "rejected"


@dataclass
class User:
    user_id: int
    username: Optional[str] = None

    # seller
    is_seller: bool = False
    seller_status: str = SELLER_STATUS_NONE
    seller_verified_phone: bool = False
    phone: Optional[str] = None

    # finance
    balance: int = 0  # внутренняя валюта

    # moderation
    is_admin: bool = False
    is_banned: bool = False

    created_at: Optional[datetime] = None


@dataclass
class Order:
    order_id: int
    buyer_id: int
    seller_id: int
    status: str
