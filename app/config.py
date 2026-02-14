import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def _csv_ints(value: str) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip().isdigit()]

@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: list[int]
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    assets_main_image_path: str = "assets/main.jpg"

def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set")

    admin_ids = _csv_ints(os.getenv("ADMIN_IDS", ""))
    db_host = os.getenv("DB_HOST", "").strip()
    db_port = int(os.getenv("DB_PORT", "5432").strip())
    db_name = os.getenv("DB_NAME", "").strip()
    db_user = os.getenv("DB_USER", "").strip()
    db_password = os.getenv("DB_PASSWORD", "").strip()

    return Config(
        bot_token=token,
        admin_ids=admin_ids,
        db_host=db_host,
        db_port=db_port,
        db_name=db_name,
        db_user=db_user,
        db_password=db_password,
    )
