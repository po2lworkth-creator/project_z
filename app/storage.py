from typing import Dict
from .models import User

# ВНИМАНИЕ: in-memory заглушка. Позже замени на SQLite/PostgreSQL.
_USERS: Dict[int, User] = {}

def get_user(user_id: int, username: str | None = None) -> User:
    u = _USERS.get(user_id)
    if not u:
        u = User(user_id=user_id, username=username)
        _USERS[user_id] = u
    else:
        if username and not u.username:
            u.username = username
    return u

def set_balance(user_id: int, amount: int) -> None:
    u = get_user(user_id)
    u.balance = amount

def add_balance(user_id: int, delta: int) -> None:
    u = get_user(user_id)
    u.balance += delta

def set_seller(user_id: int, is_seller: bool) -> None:
    u = get_user(user_id)
    u.is_seller = is_seller

def set_seller_phone_verified(user_id: int, verified: bool) -> None:
    u = get_user(user_id)
    u.seller_verified_phone = verified
