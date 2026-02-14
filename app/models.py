from dataclasses import dataclass
from typing import Optional

@dataclass
class User:
    user_id: int
    username: Optional[str] = None
    is_seller: bool = False
    seller_verified_phone: bool = False
    balance: int = 0  # внутренняя валюта (заглушка)

@dataclass
class Order:
    order_id: int
    buyer_id: int
    seller_id: int
    status: str  # created / paid / delivered / confirmed / dispute
