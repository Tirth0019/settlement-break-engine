"""
Archetype: DUPLICATE_UTR
Lifecycle: SAME_DAY

Two genuine transactions share one identifier — naive hash-join collapses them.
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
    shared_utr = make_utr(rng)
    banks = []
    settlements = []
    ledger = []
    nets = []

    for _ in range(2):
        gross = pick_gross(rng, 3000, 15000)
        fee, fee_gst, tds, net = card_settlement_amounts(gross, fee_schedule)
        nets.append(net)
        sid = f"STL-{fmt_date(date).replace('-', '')}-{rng.randint(1000, 9999)}"
        settlements.append(
            settlement_row(
                settlement_id=sid,
                utr=shared_utr,
                merchant_id=merchant,
                settled_at=date,
                gross=gross,
                fee=fee,
                fee_gst=fee_gst,
                tds=tds,
            )
        )
        banks.append(
            bank_credit_row(
                value_date=date,
                posting_date=date,
                narration=f"NEFT {shared_utr} settlement",
                amount=net,
                bank_ref=f"BNK-{rng.randint(100000, 999999)}",
            )
        )
        order_id = f"ORD-{rng.randint(100000, 999999)}"
        ledger.append(
            ledger_row(
                entry_id=f"LE-{rng.randint(100000, 999999)}",
                order_id=order_id,
                payment_id=f"PAY-{rng.randint(100000, 999999)}",
                entry_date=date,
                entry_type="sale",
                amount=gross,
                description=f"Sale {order_id}",
            )
        )
        ledger.append(
            ledger_row(
                entry_id=f"LE-{rng.randint(100000, 999999)}",
                order_id=order_id,
                payment_id="FEE",
                entry_date=date,
                entry_type="fee",
                amount=fee,
                description="PG MDR",
            )
        )
        ledger.append(
            ledger_row(
                entry_id=f"LE-{rng.randint(100000, 999999)}",
                order_id=order_id,
                payment_id="FEE",
                entry_date=date,
                entry_type="fee",
                amount=fee_gst,
                description="GST on PG fee",
            )
        )

    implied = amount_delta(banks, ledger)
    expected = ZERO  # both real; amounts balance if not collapsed
    self_check = money(implied - expected)

    return ArchetypeResult(
        rows={
            "bank_statement": banks,
            "settlement_report": settlements,
            "merchant_ledger": ledger,
        },
        ground_truth={
            "archetype": "DUPLICATE_UTR",
            "correct_verdict": "MATCH",
            "correct_residual": ZERO,
            "amount_delta": fmt_money(expected),
            "lifecycle": "SAME_DAY",
            "shared_utr": shared_utr,
            "txn_count": 2,
            "nets": [fmt_money(n) for n in nets],
        },
        self_check=self_check,
    )
