from dataclasses import dataclass

# Единый формат callback_data: "ACT:arg1:arg2"
SEP = ":"

@dataclass(frozen=True)
class Cb:
    NAV = "NAV"
    CAT = "CAT"
    WAL = "WAL"
    SUP = "SUP"
    ORD = "ORD"
    CHAT = "CHAT"
    SELL = "SELL"
    ADM = "ADM"      # admin-panel
    SAD = "SAD"      # super-admin-panel

def pack(*parts: str) -> str:
    return SEP.join(parts)

def unpack(data: str) -> list[str]:
    return data.split(SEP) if data else []
