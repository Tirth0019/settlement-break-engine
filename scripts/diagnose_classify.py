"""Classify 290 NULL: spurious L1 residual vs GT exists but join missed."""
from __future__ import annotations

import sqlite3
from collections import Counter

from sbe.engine.tools.normalise_identifier import normalise
from sbe.scoring.harness import build_match_key_index, load_ground_truth

SEED = "1001"
conn = sqlite3.connect(f"runs/sbe_{SEED}.db")
gt = load_ground_truth(SEED)
match_ix = build_match_key_index(SEED)

# Build GT lookup sets
gt_by_utr = {}
for g in gt:
    for k in ("utr", "full_utr"):
        if g.get(k):
            gt_by_utr[normalise(g[k])] = g

gt_by_tuple = {}
for g in gt:
    key = (
        g.get("merchant_id"),
        str(g.get("open_date", ""))[:10],
        f"{float(g.get('amount_delta', 0)):.2f}",
    )
    gt_by_tuple[key] = g

null_open = conn.execute(
    """
    SELECT break_id, match_key, merchant_id, amount_delta, side, first_seen_run
      FROM breaks WHERE seed=? AND status='OPEN' AND ground_truth_archetype IS NULL
    """,
    (SEED,),
).fetchall()

in_index = no_index_has_gt = no_gt = 0
side_counts = Counter()
for bid, mk, mid, amt, side, fsr in null_open:
    side_counts[side] += 1
    c = normalise(mk or "")
    if c and c in match_ix:
        in_index += 1
        continue
    tup = (mid, str(fsr)[:10], f"{float(amt):.2f}")
    if tup in gt_by_tuple:
        no_index_has_gt += 1
    elif c and c in gt_by_utr:
        no_index_has_gt += 1
    else:
        no_gt += 1

print(f"NULL OPEN total: {len(null_open)}")
print(f"  side breakdown: {dict(side_counts)}")
print(f"  match_key IN index now (pipeline should have tagged): {in_index}")
print(f"  GT exists but NOT in index: {no_index_has_gt}")
print(f"  no GT row found (spurious/CLEAN residual): {no_gt}")

# Pipeline bug: if in_index > 0 those are scoring join-only failures
# if no_index_has_gt > 0 fix build_match_key_index or pipeline timing

# Core arithmetic: confirm L1 clears FEE
from sbe.engine.pipeline import load_day_records
from sbe.engine.l1_deterministic import run as l1_run

fee_matched = fee_in_residual = 0
for g in gt:
    if g.get("archetype") != "FEE_PLUS_GST":
        continue
    day = g.get("open_day", 1)
    records = load_day_records(SEED, int(day))
    l1 = l1_run(records)
    # find settlement utr for this gt
    from sbe.engine.tools.query_sources import SourceStore
    store = SourceStore.load(SEED)
    utr = None
    for s in store.settlement:
        if (
            s.get("merchant_id") == g.get("merchant_id")
            and str(s.get("settled_at", ""))[:10] == str(g.get("open_date", ""))[:10]
            and str(s.get("gross_amount")) == str(g.get("gross_amount"))
        ):
            utr = normalise(s.get("utr") or "")
            break
    if not utr:
        continue
    in_matched = any(m.get("join_key") == utr for m in l1.get("matched") or [])
    in_res = any(r.get("match_key") == utr or r.get("join_key") == utr for r in l1.get("residual") or [])
    if in_matched:
        fee_matched += 1
    if in_res:
        fee_in_residual += 1

print(f"\nFEE_PLUS_GST GT rows checked via day reload:")
print(f"  L1 matched (bank=settlement net): {fee_matched}")
print(f"  L1 residual: {fee_in_residual}")

conn.close()
