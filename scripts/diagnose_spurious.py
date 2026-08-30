"""Diagnose 290 spurious L1 residuals — key mismatch vs missing GT."""
from __future__ import annotations

import sqlite3
from collections import Counter

from sbe.engine.pipeline import load_day_records, _seed_start_date
from sbe.engine.tools.normalise_identifier import identifiers_compatible, normalise
from sbe.engine.l1_deterministic import hash_join_key
from sbe.engine.tools.query_sources import SourceStore
from datetime import date, timedelta

SEED = "1001"
conn = sqlite3.connect(f"runs/sbe_{SEED}.db")
store = SourceStore.load(SEED)
start = _seed_start_date(SEED)

null_open = conn.execute(
    """
    SELECT break_id, match_key, merchant_id, side, amount_delta, first_seen_run
      FROM breaks WHERE seed=? AND status='OPEN' AND ground_truth_archetype IS NULL
    """,
    (SEED,),
).fetchall()

# Build settlement/bank indexes by merchant for fuzzy lookup
sett_by_merch: dict[str, list] = {}
bank_by_merch: dict[str, list] = {}
for s in store.settlement:
    sett_by_merch.setdefault(s.get("merchant_id", ""), []).append(s)
for b in store.bank:
    bank_by_merch.setdefault(b.get("merchant_id", ""), []).append(b)

exact_counterpart = compat_counterpart = no_counterpart = 0
key_mismatch_samples = []
amount_mismatch = 0

for bid, mk, mid, side, amt, fsr in null_open[:100]:  # sample 100
    canon = normalise(mk or "")
    found_exact = False
    found_compat = False
    # opposite source
    if side == "SETTLEMENT_ONLY":
        pool = bank_by_merch.get(mid, [])
        for b in pool:
            bkey = hash_join_key({**b, "_source": "bank_statement"})
            if bkey == canon:
                found_exact = True
                break
            if identifiers_compatible(mk or "", b.get("narration") or bkey):
                found_compat = True
                if len(key_mismatch_samples) < 5:
                    key_mismatch_samples.append(
                        (side, mk, bkey, b.get("narration", "")[:60])
                    )
    else:  # BANK_ONLY
        pool = sett_by_merch.get(mid, [])
        for s in pool:
            skey = normalise(s.get("utr") or "")
            if skey == canon:
                found_exact = True
                break
            if identifiers_compatible(mk or "", s.get("utr") or ""):
                found_compat = True
                if len(key_mismatch_samples) < 5:
                    key_mismatch_samples.append((side, mk, skey, s.get("utr")))

    if found_exact:
        exact_counterpart += 1
    elif found_compat:
        compat_counterpart += 1
    else:
        no_counterpart += 1

print(f"Sampled 100 NULL OPEN breaks:")
print(f"  exact key counterpart exists: {exact_counterpart}")
print(f"  compatible-but-not-exact key: {compat_counterpart}")
print(f"  no counterpart at all: {no_counterpart}")
print("  key mismatch samples:", key_mismatch_samples)

# Day-level: how many L1 residuals are CLEAN (no GT) vs fixable join
from sbe.scoring.harness import load_ground_truth

gt_utrs = set()
for g in load_ground_truth(SEED):
    for k in ("utr", "full_utr"):
        if g.get(k):
            gt_utrs.add(normalise(g[k]))
    # settlement link
    mid, od, gross = g.get("merchant_id"), str(g.get("open_date", ""))[:10], g.get("gross_amount")
    if mid and od and gross:
        for s in store.settlement:
            if s.get("merchant_id") == mid and str(s.get("settled_at", ""))[:10] == od:
                if str(s.get("gross_amount")) == str(gross):
                    gt_utrs.add(normalise(s.get("utr") or ""))

total_spurious_l1 = 0
fixable_trunc = 0
for day in range(1, 11):
    records = load_day_records(SEED, day)
    from sbe.engine.l1_deterministic import run as l1_run

    l1 = l1_run(records)
    for item in l1.get("residual") or []:
        mk = item.get("match_key") or item.get("join_key") or ""
        if normalise(mk) in gt_utrs:
            continue  # labeled archetype residual
        total_spurious_l1 += 1
        key = hash_join_key(
            (item.get("settlement") or item.get("bank") or {})
            | {"_source": "settlement_report" if item.get("settlement") else "bank_statement"}
        )
        opp = store.settlement if item.get("bank") else store.bank
        for row in opp:
            other = row.get("utr") or row.get("narration") or ""
            if identifiers_compatible(mk, other) and normalise(mk) != normalise(other):
                fixable_trunc += 1
                break

print(f"\nAcross 10 days L1 residuals without GT label: ~{total_spurious_l1} (cumulative count)")
print(f"  of which truncation-compatible key exists: {fixable_trunc} (heuristic)")

conn.close()
