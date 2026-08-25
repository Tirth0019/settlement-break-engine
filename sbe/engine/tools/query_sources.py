"""query_bank / query_settlement / query_ledger tools — read-only lookups
the investigator and verifier call to pull related rows for a given break.
Kept as plain deterministic queries; never LLM-interpreted."""

def query_bank(merchant_id: str, date_range: tuple, conn) -> list:
    raise NotImplementedError


def query_settlement(merchant_id: str, date_range: tuple, conn) -> list:
    raise NotImplementedError


def query_ledger(merchant_id: str, date_range: tuple, conn) -> list:
    raise NotImplementedError
