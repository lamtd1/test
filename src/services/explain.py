"""Sinh reasons/tradeoffs bằng template — không gọi LLM. Mỗi câu phải sinh từ một
field cụ thể; không có field thì không có câu (xem docs/prototype-plan.md Bước 4)."""

from datetime import date

from src.models.criteria import CriteriaSchema
from src.models.envelop import Envelope
from src.services.retrieval import DIR_VI, ScoredUnit


def _ty(vnd: int) -> str:
    return f"{vnd / 1_000_000_000:.2f} tỷ"


def build_reasons(scored: ScoredUnit) -> list[str]:
    reasons: list[str] = []
    row = scored.row

    for poi_name, d in scored.poi_distances.items():
        d = round(d)
        reasons.append(f"Cách {poi_name} {d}m — đi bộ {d // 75} phút")

    if row["balcony_dir"] is not None:
        reasons.append(
            f"Tầng {row['floor']}/{row['total_floors']}, "
            f"ban công {DIR_VI.get(row['balcony_dir'], row['balcony_dir'])}, "
            f"{row['n_open_sides'] or '?'} mặt thoáng"
        )
    else:
        reasons.append(f"Tầng {row['floor']}/{row['total_floors']}")

    return reasons[:3]


def build_tradeoffs(scored: ScoredUnit, envelope: Envelope) -> list[str]:
    tradeoffs: list[str] = []
    row = scored.row
    price = row["price_vnd"]

    if price > envelope.price_target_vnd:
        over = (price / envelope.price_target_vnd - 1) * 100
        tradeoffs.append(f"Giá {_ty(price)} — vượt vùng thoải mái của bạn {over:.0f}%")

    if row["balcony_dir"] == "W":
        tradeoffs.append("Ban công hướng Tây — nắng chiều gắt hơn các hướng khác")

    handover_date = row["handover_date"]
    if handover_date is not None and date.fromisoformat(handover_date) > date.today():
        tradeoffs.append(f"Bàn giao {handover_date} — chưa nhận nhà ngay được")

    if not tradeoffs:
        tradeoffs.append("Không có đánh đổi đáng kể so với tiêu chí của bạn")

    return tradeoffs


def explain(scored: ScoredUnit, criteria: CriteriaSchema, envelope: Envelope) -> tuple[list[str], list[str]]:
    return build_reasons(scored), build_tradeoffs(scored, envelope)
