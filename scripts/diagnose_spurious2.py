"""Spurious breaks: amount mismatch vs key mismatch."""
from __future__ import annotations

import sqlite3

from sbe.engine.l1_deterministic import hash_join_key, _row_amount
from sbe.engine.tools.normalise_identifier import normalise
from sbe.engine.tools.query_sources import SourceStore

SEED = "1001"
conn = sqlite3.connect(f"runs/sbe_{SEED}.db")
store = SourceStore.load(SEED)

rows = conn.execute(
    """
    SELECT break_id, match_key, merchant_id, side, amount_delta
      FROM breaks WHERE seed=? AND status='OPEN' AND ground_truth_archetype IS NULL
     LIMIT 100
    """,
    (SEED,),
).fetchall()

amt_mismatch = key_missing = matched_would = 0
samples = []

for bid, mk, mid, side, amt in rows:
    canon = normalise(mk or "")
    if side == "SETTLEMENT_ONLY":
        srows = [s for s in store.settlement if normalise(s.get("utr") or "") == canon]
        brows = [b for b in store.bank if hash_join_key({**b, "_source": "bank_statement"}) == canon]
        if not srows:
            key_missing += 1
            continue
        s_amt = float(srows[0].get("net_amount", 0))
        if brows:
            for b in brows:
                b_amt = float(_row_amount(b))
                if b_amt == s_amt:
                    matched_would += 1
                    break
            else:
                amt_mismatch += 1
                if len(samples) < 5:
                    samples.append(("SETT_ONLY", mk, s_amt, [float(_row_amount(b)) for b in brows[:3]]))
        else:
            key_missing += 1
    else:  # BANK_ONLY
        brows = [b for b in store.bank if hash_join_key({**b, "_source": "bank_statement"}) == canon]
        srows = [s for s in store.settlement if normalise(s.get("utr") or "") == canon]
        if not brows:
            key_missing += 1
            continue
        b_amt = float(_row_amount(brows[0]))
        if srows:
            for s in srows:
                s_amt = float(s.get("net_amount") or 0)
                if s_amt == b_amt:
                    matched_would += 1
                    break
            else:
                amt_mismatch += 1
                if len(samples) < 5:
                    samples.append(("BANK_ONLY", mk, b_amt, [float(s.get("net_amount") or 0) for s in srows[:3]]))
        else:
            key_missing += 1

print("100 NULL OPEN sample:")
print(f"  would match if re-run L1 on same keys (amt equal): {matched_would}")
print(f"  key exists both sides but AMOUNT mismatch: {amt_mismatch}")
print(f"  key missing on one side: {key_missing}")
print("amount mismatch samples (side, mk, primary_amt, other_amts):", samples)

# Multi-settlement same UTR?
from collections import Counter
utr_counts = Counter(normalise(s.get("utr") or "") for s in store.settlement)
dup_utrs = [u for u, c in utr_counts.items() if c > 1 and u]
print(f"\nduplicate settlement UTRs: {len(dup_utrs)}")

conn.close()
