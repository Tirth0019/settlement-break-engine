"""
Archetype: SPLIT_SETTLEMENT_N1 / SPLIT_SETTLEMENT_1N
Lifecycle: SAME_DAY

N:1 — several ledger sales settle as one bank credit (subset-sum).
1:N — one settlement splits across multiple bank credits.
"""
from sbe.generator.archetypes._helpers import (
    amount_delta,
    bank_credit_row,
    card_settlement_amounts,
    fmt_date,
    fmt_money,
    ledger_row,
    make_utr,
    pick_gross,
    settlement_row,
)
from sbe.generator.archetypes.base import ArchetypeResult
from sbe.money import ZERO, money


def generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult:
    if rng.random() < 0.5:
        return _generate_n1(rng, merchant, date, fee_schedule)
    return _generate_1n(rng, merchant, date, fee_schedule)


def _generate_n1(rng, merchant, date, fee_schedule) -> ArchetypeResult:
    parts = [pick_gross(rng, 2000, 8000) for _ in range(rng.randint(2, 4))]
    gross = money(sum(parts))
    fee, fee_gst, tds, net = card_settlement_amounts(gross, fee_schedule)
    utr = make_utr(rng)

    settlement = settlement_row(
        settlement_id=f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}",
        utr=utr,
        merchant_id=merchant,
        settled_at=date,
        gross=gross,
        fee=fee,
        fee_gst=fee_gst,
        tds=tds,
        txn_count=len(parts),
    )
    bank = bank_credit_row(
        value_date=date,
        posting_date=date,
        narration=f"NEFT {utr} batch settle",
        amount=net,
        bank_ref=f"BNK-{rng.randint(100000, 999999)}",
    )
    ledger = []
    for part in parts:
        order_id = f"ORD-{rng.randint(100000, 999999)}"
        ledger.append(
            ledger_row(
                entry_id=f"LE-{rng.randint(100000, 999999)}",
                order_id=order_id,
                payment_id=f"PAY-{rng.randint(100000, 999999)}",
                entry_date=date,
                entry_type="sale",
                amount=part,
                description=f"Sale {order_id} in N:1 batch",
            )
        )
    # Fees booked once against the batch
    ledger.append(
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id="BATCH",
            payment_id="BATCH",
            entry_date=date,
            entry_type="fee",
            amount=fee,
            description="Batch MDR",
        )
    )
    ledger.append(
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id="BATCH",
            payment_id="BATCH",
            entry_date=date,
            entry_type="fee",
            amount=fee_gst,
            description="Batch GST on fee",
        )
    )

    implied = amount_delta([bank], ledger)
    expected = ZERO  # fully explained N:1 — bank equals ledger net
    self_check = money(implied - expected)

    return ArchetypeResult(
        rows={
            "bank_statement": [bank],
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "SPLIT_SETTLEMENT_N1",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected),
            "lifecycle": "SAME_DAY",
            "part_count": len(parts),
            "part_grosses": [fmt_money(p) for p in parts],
        },
        self_check=self_check,
    )


def _generate_1n(rng, merchant, date, fee_schedule) -> ArchetypeResult:
    gross = pick_gross(rng)
    fee, fee_gst, tds, net = card_settlement_amounts(gross, fee_schedule)
    # Split net into 2-3 bank credits
    n = rng.randint(2, 3)
    slices = []
    remaining = net
    for i in range(n - 1):
        piece = money(rng.randint(100, max(101, int(remaining) // (n - i + 1))))
        slices.append(piece)
        remaining = money(remaining - piece)
    slices.append(remaining)

    utr = make_utr(rng)
    settlement = settlement_row(
        settlement_id=f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}",
        utr=utr,
        merchant_id=merchant,
        settled_at=date,
        gross=gross,
        fee=fee,
        fee_gst=fee_gst,
        tds=tds,
    )
    banks = [
        bank_credit_row(
            value_date=date,
            posting_date=date,
            narration=f"NEFT {utr} part{i+1}/{n}",
            amount=piece,
            bank_ref=f"BNK-{rng.randint(100000, 999999)}",
        )
        for i, piece in enumerate(slices)
    ]
    ledger = [
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id=f"ORD-{rng.randint(100000, 999999)}",
            payment_id=f"PAY-{rng.randint(100000, 999999)}",
            entry_date=date,
            entry_type="sale",
            amount=gross,
            description="Sale settled 1:N across bank credits",
        ),
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id="FEE",
            payment_id="FEE",
            entry_date=date,
            entry_type="fee",
            amount=fee,
            description="PG MDR",
        ),
        ledger_row(
            entry_id=f"LE-{rng.randint(100000, 999999)}",
            order_id="FEE",
            payment_id="FEE",
            entry_date=date,
            entry_type="fee",
            amount=fee_gst,
            description="GST on PG fee",
        ),
    ]

    implied = amount_delta(banks, ledger)
    expected = ZERO
    self_check = money(implied - expected)

    return ArchetypeResult(
        rows={
            "bank_statement": banks,
            "settlement_report": [settlement],
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "SPLIT_SETTLEMENT_1N",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected),
            "lifecycle": "SAME_DAY",
            "bank_credit_count": n,
            "slices": [fmt_money(s) for s in slices],
        },
        self_check=self_check,
    )
