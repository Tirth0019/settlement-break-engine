"""find_split_candidates tool — bounded subset-sum search for N:1 / 1:N
split-settlement reconstruction (BUILD_PLAN L6: subset-sum tool; keep bounded,
this is not a general knapsack solver)."""
from decimal import Decimal


def find_split_candidates(target_amount: Decimal, candidate_amounts: list, max_n: int = 4) -> list:
    """Returns subsets of candidate_amounts summing to target_amount, capped
    at max_n items to keep this bounded and fast."""
    raise NotImplementedError
