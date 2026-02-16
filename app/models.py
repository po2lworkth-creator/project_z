from dataclasses import dataclass
from typing import Optional

# seller_status:
# - "none"     - пользователь не продавец и не подавал заявку
# - "applied"  - заявка подана, ждёт решения администраторов
# - "seller"   - роль продавца выдана
# - "rejected" - заявка отклонена
SELLER_STATUS_NONE = "none"
SELLER_STATUS_APPLIED = "applied"
SELLER_STATUS_SELLER = "seller"
SELLER_STATUS_REJECTED = "rejected"


@dataclass
class User:
    user_id: int
    username: Optional[str] = None

    #Telegram contact
    phone: Optional[str] = None
    seller_verified_phone: bool = False

    is_seller: bool = False
    seller_status: str = SELLER_STATUS_NONE

    balance: int = 0  # внутренняя валюта (заглушка)


@dataclass
class Order:
    order_id: int
    buyer_id: int
    seller_id: int
    status: str  # created / paid / delivered / confirmed / dispute
