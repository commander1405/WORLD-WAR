"""Equipment stats, readiness and combat consumption helpers."""
from __future__ import annotations

import math
from typing import Any

from modules.ng.catalog import CATALOG

_CAT = {c["item_code"]: c for c in CATALOG}

# How many use-charges one purchased specialist unit grants
SPECIALIST_CHARGES_PER_UNIT = 2


def meta(code: str) -> dict[str, Any] | None:
    return _CAT.get(code)


def damage_of(code: str) -> float:
    m = _CAT.get(code) or {}
    return float(m.get("damage") if m.get("damage") is not None else m.get("power_score") or 0)


def defense_of(code: str) -> float:
    m = _CAT.get(code) or {}
    return float(m.get("defense") or 0)


def accuracy_of(code: str) -> float:
    m = _CAT.get(code) or {}
    return float(m.get("accuracy") or 50)


def consumption_type(code: str) -> str:
    m = _CAT.get(code) or {}
    return str(m.get("consumption_type") or "sortie")


def is_combat_category(cat: str, kind: str) -> bool:
    if kind == "ground":
        return cat in ("ground", "missile")
    if kind == "air":
        return cat in ("air", "missile")
    if kind == "sea":
        return cat in ("sea", "missile")
    if kind == "defense":
        return cat in ("defense", "missile")
    return False


def missile_matches_kind(code: str, kind: str) -> bool:
    ground_m = {"m_cruise", "m_ballistic", "m_agm", "m_cruise_adv", "m_icbm_game"}
    air_m = {"m_aam", "m_agm"}
    sea_m = {"m_antiship"}
    if kind == "ground":
        return code in ground_m
    if kind == "air":
        return code in air_m or code in ground_m
    if kind == "sea":
        return code in sea_m or code == "m_cruise"
    return False


def engage_quantity(qty: float, percent: float, *, item_code: str | None = None) -> float:
    """Units committed this operation (percent of stock). Missiles = whole units only."""
    ratio = max(0.0, min(1.0, percent / 100.0))
    use = qty * ratio
    if use <= 0:
        return 0.0
    # missiles / expendable one-shot: whole numbers only
    cat = str((_CAT.get(item_code) or {}).get("category") or "") if item_code else ""
    ctype = consumption_type(item_code) if item_code else ""
    if cat == "missile" or ctype == "expendable" or (item_code and str(item_code).startswith("m_")):
        use = max(1.0, float(math.floor(use + 1e-9))) if qty >= 1 else 0.0
        return min(qty, use)
    # at least 1 unit if stock >= 1 and percent >= 10
    if qty >= 1 and use < 1 and percent >= 10:
        return 1.0
    return use


def consume_amount(
    code: str,
    engaged: float,
    *,
    victory: bool,
    specialist_bonus_logistics: bool = False,
) -> float:
    """
    How many inventory units to deduct after an operation.
    - expendable / missile: all engaged (each missile once)
    - sortie: attrition only (units return from mission)
    - specialist: 1 charge per use (caller handles)
    """
    ctype = consumption_type(code)
    cat = str((_CAT.get(code) or {}).get("category") or "")
    if engaged <= 0:
        return 0.0
    if ctype == "expendable" or cat == "missile" or str(code).startswith("m_"):
        return float(math.ceil(engaged - 1e-9))
    if ctype == "specialist":
        return 1.0  # one charge
    if ctype in ("passive", "building"):
        return 0.0
    # sortie: operational attrition — not full delete
    rate = 0.04 if victory else 0.12
    if specialist_bonus_logistics:
        rate *= 0.5
    loss = engaged * rate
    # fractional ok for large stacks; for small, round carefully
    if engaged >= 1:
        loss = max(0.0, loss)
    return float(min(engaged, loss))


def attack_power_for_unit(code: str, qty_engaged: float) -> float:
    m = _CAT.get(code) or {}
    dmg = damage_of(code)
    acc = accuracy_of(code) / 100.0
    tech = float(m.get("technology_level") or 1)
    return dmg * qty_engaged * (0.7 + 0.3 * acc) * (0.9 + 0.05 * tech)


def defense_power_for_unit(code: str, qty: float) -> float:
    m = _CAT.get(code) or {}
    defn = defense_of(code)
    tech = float(m.get("technology_level") or 1)
    return defn * qty * (0.9 + 0.05 * tech)
