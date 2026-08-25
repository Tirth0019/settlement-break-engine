"""GATE 3 — fee_recompute must reproduce every generator-computed fee
exactly, to the paise, for every archetype. Part of make daily-check."""
import random
from datetime import date
from decimal import Decimal

from sbe.engine.tools.banking_calendar import load_calendar
from sbe.engine.tools.fee_recompute import (
    load_fee_schedule,
    recompute_chargeback_fee,
    recompute_fee,
    recompute_gst_on_fee,
    recompute_instant_settlement_fee,
    recompute_tds_194o,
)
from sbe.generator.archetypes.registry import ALL_MODULES, generate_clean
from sbe.money import money


def test_fee_recompute_matches_every_archetype():
    fee_schedule = load_fee_schedule()
    calendar = dict(load_calendar())
    calendar["_merchant_state"] = "Gujarat"
    rng = random.Random(20260318)

    for module in ALL_MODULES:
        result = module.generate(rng, "MERCH_0003", date(2026, 3, 18), fee_schedule, calendar)
        arch = result.ground_truth["archetype"]

        for row in result.rows.get("settlement_report") or []:
            gross = money(row["gross_amount"])
            stated_fee = money(row["fee"])
            stated_gst = money(row["fee_gst"])
            stated_tds = money(row["tds"])
            stype = row.get("settlement_type") or "standard"

            if stype == "reserve_release":
                assert stated_fee == money(0)
                assert stated_gst == money(0)
                continue

            if stype == "instant":
                base = recompute_fee(gross, "card", fee_schedule)
                instant = recompute_instant_settlement_fee(gross, fee_schedule)
                expect_fee = money(base + instant)
                expect_gst = money(
                    recompute_gst_on_fee(base, fee_schedule)
                    + recompute_gst_on_fee(instant, fee_schedule)
                )
            elif stype == "upi":
                expect_fee = recompute_fee(gross, "upi", fee_schedule)
                expect_gst = recompute_gst_on_fee(expect_fee, fee_schedule)
            elif stype == "international":
                expect_fee = recompute_fee(gross, "international", fee_schedule)
                expect_gst = recompute_gst_on_fee(expect_fee, fee_schedule)
            else:
                expect_fee = recompute_fee(gross, "card", fee_schedule)
                expect_gst = recompute_gst_on_fee(expect_fee, fee_schedule)

            # TDS may or may not apply depending on archetype
            if stated_tds != money(0):
                assert stated_tds == recompute_tds_194o(gross, fee_schedule), arch

            assert stated_fee == expect_fee, f"{arch}: fee {stated_fee} != {expect_fee}"
            assert stated_gst == expect_gst, f"{arch}: gst {stated_gst} != {expect_gst}"

        # Chargeback path has no settlement fee rows — check schedule tool directly
        if arch == "CHARGEBACK_PLUS_FEE":
            assert recompute_chargeback_fee(fee_schedule) == money("400.00")
            assert recompute_gst_on_fee(money("400.00"), fee_schedule) == money("72.00")

    # CLEAN smoke
    clean = generate_clean(rng, "MERCH_0001", date(2026, 3, 18), fee_schedule, calendar)
    row = clean.rows["settlement_report"][0]
    gross = money(row["gross_amount"])
    assert money(row["fee"]) == recompute_fee(gross, "card", fee_schedule)
    assert money(row["fee_gst"]) == recompute_gst_on_fee(money(row["fee"]), fee_schedule)
