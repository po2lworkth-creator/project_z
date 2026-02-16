from dataclasses import dataclass
from typing import Optional


SELLER_STATUS_NONE = "none"
SELLER_STATUS_APPLIED = "applied"
SELLER_STATUS_SELLER = "seller"
SELLER_STATUS_REJECTED = "rejected"


@dataclass
class User:
    user_id: int
    username: Optional[str] = None

    # продавец
    is_seller: bool = False
    seller_status: str = SELLER_STATUS_NONE

    # телефон
    phone: Optional[str] = None
    seller_verified_phone: bool = False

    # баланс
    balance: int = 0


@dataclass
class Order:
    order_id: int
    buyer_id: int
    seller_id: int
    status: str  #