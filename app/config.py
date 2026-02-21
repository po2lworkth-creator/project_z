import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _csv_ints(value: str) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip().isdigit()]


def _unique_ints(values: list[int]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out


@dataclass(frozen=True)
class Config:
    bot_token: str
    super_admin_ids: list[int]
    support_ids: list[int]
    admin_ids: list[int]
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    assets_main_image_path: str = "assets/main.jpg"
    stars_provider_token: str = ""
    topup_balance_per_star: int = 2
    crypto_bot_api_token: str = ""
    yoomoney_oauth_token: str = ""
    yoomoney_wallet: str = ""
    yoomoney_payment_type: str = "SB"

    @property
    def super_admin_id(self) -> int:
        # Backward-compatible alias for legacy call sites.
        return int(self.super_admin_ids[0])


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    # Accept both legacy SUPER_ADMIN_ID and SUPER_ADMIN_IDS. Both support CSV.
    super_admin_raw = os.getenv("SUPER_ADMIN_IDS", "").strip() or os.getenv("SUPER_ADMIN_ID", "").strip()
    super_admin_ids = _csv_ints(super_admin_raw)
    if not super_admin_ids:
        raise RuntimeError("SUPER_ADMIN_ID/SUPER_ADMIN_IDS is not set")

    admin_ids_raw = _csv_ints(os.getenv("ADMIN_IDS", ""))
    support_ids_raw = _unique_ints(_csv_ints(os.getenv("SUPPORT_IDS", "")))
    support_ids = support_ids_raw if support_ids_raw else list(super_admin_ids)
    # Super-admins are always admins as well.
    admin_ids = _unique_ints([*super_admin_ids, *admin_ids_raw])
    db_host = os.getenv("DB_HOST", "").strip()
    db_port = int(os.getenv("DB_PORT", "5432").strip())
    db_name = os.getenv("DB_NAME", "").strip()
    db_user = os.getenv("DB_USER", "").strip()
    db_password = os.getenv("DB_PASSWORD", "").strip()
    stars_provider_token = os.getenv("STARS_PROVIDER_TOKEN", "").strip()
    topup_balance_raw = os.getenv("TOPUP_BALANCE_PER_STAR", "2").strip() or "2"
    try:
        topup_balance_per_star = int(topup_balance_raw)
    except ValueError:
        topup_balance_per_star = 2
    if topup_balance_per_star <= 0:
        topup_balance_per_star = 1
    crypto_bot_api_token = os.getenv("CRYPTO_BOT_API_TOKEN", "").strip()
    yoomoney_oauth_token = os.getenv("YOOMONEY_OAUTH_TOKEN", "").strip()
    yoomoney_wallet = os.getenv("YOOMONEY_WALLET", "").strip()
    yoomoney_payment_type = os.getenv("YOOMONEY_PAYMENT_TYPE", "SB").strip() or "SB"

    return Config(
        bot_token=token,
        super_admin_ids=super_admin_ids,
        support_ids=support_ids,
        admin_ids=admin_ids,
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_user=db_user,
        db_password=db_password,
        stars_provider_token=stars_provider_token,
        topup_balance_per_star=topup_balance_per_star,
        crypto_bot_api_token=crypto_bot_api_token,
        yoomoney_oauth_token=yoomoney_oauth_token,
        yoomoney_wallet=yoomoney_wallet,
        yoomoney_payment_type=yoomoney_payment_type,
    )
