"""find_split_candidates tool — bounded subset-sum search for N:1 / 1:N
split-settlement reconstruction (BUILD_PLAN L6: subset-sum tool; keep bounded,
this is not a general knapsack solver)."""
from __future__ import annotations

from decimal import Decimal
from itertools import combinations
from typing import Any

from sbe.money import money


def find_split_candidates(
    target_amount: Decimal,
    candidate_amounts: list,
    max_n: int = 4,
    *,
    tolerance: Decimal | None = None,
) -> list[dict[str, Any]]:
    """Return subsets of ``candidate_amounts`` summing to ``target_amount``.

    Each candidate may be a Decimal/str/number or a dict with an ``amount``
    (or ``credit`` / ``net_amount``) field. Capped at ``max_n`` items.
    ``tolerance`` defaults to exact paise match (₹0.00).
    """
    target = money(target_amount)
    tol = money(tolerance) if tolerance is not None else money(0)
    if max_n < 1:
        return []

    indexed: list[tuple[int, Decimal, Any]] = []
    for i, raw in enumerate(candidate_amounts):
        if isinstance(raw, dict):
            amt = raw.get("amount")
            if amt in (None, ""):
                amt = raw.get("credit") or raw.get("net_amount") or raw.get("debit")
            indexed.append((i, money(amt or 0), raw))
        else:
            indexed.append((i, money(raw), raw))

    out: list[dict[str, Any]] = []
    seen: set[tuple[int, ...]] = set()
    for n in range(1, min(max_n, len(indexed)) + 1):
        for combo in combinations(indexed, n):
            total = money(sum(a for _, a, _ in combo))
            if abs(total - target) <= tol:
                idxs = tuple(sorted(i for i, _, _ in combo))
                if idxs in seen:
                    continue
                seen.add(idxs)
                out.append(
                    {
                        "indices": list(idxs),
                        "sum": f"{total:.2f}",
                        "items": [item for _, _, item in combo],
                    }
                )
    return out
