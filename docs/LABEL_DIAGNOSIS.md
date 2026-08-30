# Label diagnosis (seed 1001)

**Date:** 2026-08-29 (Phase 5, pre-L1 fix) · **Updated:** 2026-08-30 (post-L1 fix)  
**Artifact:** dated diagnosis for KNOWN_ISSUES / submission scars

Re-run queries: `python scripts/diagnose_classify.py`, `python scripts/diagnose_spurious2.py`  
Verify gate: `sbe check surfacing --seed 1001`

---

## Aug 30 after L1 three-way fix (same seed 1001, regenerated)

| Metric | Before (Aug 29) | After (Aug 30) |
|---|---|---|
| OPEN breaks, `ground_truth_archetype IS NULL` | **290** | **57** |
| 100-NULL sample: same key, **amount mismatch** | **75** | **0** |
| 100-NULL sample: key missing one side | 19 | 37 |
| OPEN breaks with label | 47 | **391** |
| Injected archetypes missing from OPEN pool | 13 | **4** |
| `sbe run` roll-forward | tied | **tied** (10 days) |
| Avg L1 clear rate | ~70% (misleading) | **56.7%** (real) |

**Core trio now surfaces:** `FEE_PLUS_GST` 54, `TDS_194O` 44, `CHARGEBACK_PLUS_FEE` 26 OPEN with labels.

**Still missing OPEN (4):** `BANK_CUTOFF_ROLLOVER`, `DUPLICATE_UTR`, `FX_ROUNDING_DRIFT`, `STATE_HOLIDAY_SHIFT` — multi-day / duplicate-UTR edge cases; 57 residual unlabeled breaks are mostly cross-day `BANK_ONLY`/`SETTLEMENT_ONLY`.

**Dense scoring seed:** `2001` (`sbe generate --seed 2001 --dense`) — 280 records, **172 labelled OPEN** breaks after `sbe run` (target was ~120–150; landed slightly high, not the 47-break fallback).

**L4 quota (locked):** separate **Google** verifier family — see `docs/INVESTIGATOR_QUOTA.md` § L4 verifier quota.

---

## Executive summary — two defects, both break headline metrics (pre-fix)

| Defect | Gate 5 impact | Headline / exception-list impact |
|---|---|---|
| **290 spurious OPEN breaks (UNKNOWN)** | Pool is 86% noise | **% value reconciled understated**; exception list is mostly unexplained breaks; **70.6% L1 clear rate is not real** |
| **Ledger-blind L1 (core trio)** | FEE/TDS/CHARGEBACK never open | Arithmetic archetypes unscorable |

**Fix order:** spurious 290 **first** (likely one systematic join cause), then **three-way L1** (bank + settlement + ledger, normalised keys).

Gate 3 validated generator **arithmetic**, not that L1 **surfaces** injected defects. Gate 3b added: `sbe check surfacing`.

---

## 290/337 UNKNOWN — spurious L1 residuals (worse finding)

All 290 OPEN breaks with `ground_truth_archetype IS NULL` have **no `ground_truth.jsonl` row** — not a scoring join bug.

Sample of 100 (2026-08-29 query):

| Cause | Count | Notes |
|---|---|---|
| **Same UTR/key both sides, amount mismatch** | **75** | Bank credit ≠ settlement `net_amount` on same canonical key (~₹300 deltas — fee/GST scale) |
| Key missing on one side | 19 | True BANK_ONLY / SETTLEMENT_ONLY |
| Would match on re-run (amt equal) | 6 | |
| Truncation (`identifiers_compatible` only) | ~11/day heuristic | **Not** the dominant cause |

Side mix (all 290): **200 BANK_ONLY**, **90 SETTLEMENT_ONLY**.

**Hypothesis (confirmed):** L1 was a **two-way exact hash-join on amount + key**, run **per day**. Same-key fee-scale deltas (including `TRUE_LEAKAGE`) and ledger-blind clears inflated noise. **Fix:** key-first join, `fee_recompute` reconcile for bank↔settlement, ledger arm for `AMOUNT_MISMATCH`.

---

## FEE_PLUS_GST = 0 — ledger-blind L1 (fixed Aug 30)

- **54** GT labels; previously **54/54** L1-cleared with no ledger compare.
- **Now:** 54 OPEN `AMOUNT_MISMATCH` breaks with `FEE_PLUS_GST` labels.

Same pattern restored for **TDS_194O**, **CHARGEBACK_PLUS_FEE**, **INSTANT_SETTLEMENT_FEE**, etc.

---

## Planned remediation (Aug 30) — status

1. **Fix spurious 290:** ✅ key-first join + fee reconcile; amount-mismatch bucket → 0 in 100-NULL sample; NULL OPEN 290 → 57.
2. **Ledger arm:** ✅ `AMOUNT_MISMATCH` when ledger net ≠ bank for matched txn.
3. **Dense seed:** ✅ seed **2001**, 280 records, 172 labelled OPEN (`--dense`).
4. **`sbe check surfacing`:** ⚠️ fails on **4 cut archetypes** (explicit scope decision — see `KNOWN_ISSUES.md`) + 57 cross-day unlabeled OPEN.

---

## Scope cuts (Aug 30)

Four injected archetypes are **not** surfaced by L1 and are **cut for time**:
`BANK_CUTOFF_ROLLOVER`, `DUPLICATE_UTR`, `FX_ROUNDING_DRIFT`, `STATE_HOLIDAY_SHIFT`.
All require multi-day or duplicate-key handling L1 does not implement. The generator
labels them; Gate 3b names the gap — that is the check working as designed.

**57 unlabeled OPEN** (down from 290): cross-day bank/settlement arrival; per-day L1
cannot re-pair across days. Named residual, not silent noise.

---

## Quota / reporting strategy

~200 L3 calls left in project; **~100 reserved for hold-out 9999**.

Dense pool → investigate **whole pool** on seed 2001 (172 labelled OPEN). Report: *"L1 at 1,000 records (seed 1001); full agent scoring on dense seed 2001 (172 breaks)."*

---

## Schedule (freeze Sep 1)

| Day | Work |
|---|---|
| **Aug 30** | Fix 290 + three-way L1. Regenerate dense seed. `sbe run` → surfacing gate green. **No L3.** |
| **Aug 31** | `--smoke` trio → full L3 dense pool → verify → score. Gates 5 & 6. |
| **Sep 1** | Table, leakage recall, cost/break. **Freeze.** 9999 generate + hold-out run. |
| **Sep 2–5** | Deliverables, demo, buffer, submit. |

**Cuts:** calibration/ECE, coverage curve (too few points in dense pool).

**Fallback:** if L1 fix cascades, freeze L1 as-is, score 47 labelled breaks only, report honestly. **Not needed** — dense seed landed at 172 labelled OPEN.

---

## What actually opens today (seed 1001, post-fix)

L1 surfaces ledger variance (`AMOUNT_MISMATCH`) and timing sides (`BANK_ONLY` / `SETTLEMENT_ONLY`) with GT match-key indexing. Top OPEN labelled archetypes: `TRUE_LEAKAGE` (75), `FEE_PLUS_GST` (54), `TDS_194O` (44), `SPLIT_SETTLEMENT_1N` (40), …
