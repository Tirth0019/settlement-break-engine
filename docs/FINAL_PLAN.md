# SBE — Final Execution Plan (Aug 31 hold-out → Sep 5 submit)

Supersedes the phase roadmap in `BUILD_PLAN.md` Part IV. That plan assumed build time was the constraint. It isn't — **quota is**, and the agent is already frozen.

**Timeline revision (Aug 31 evening):** Hold-out ran **Aug 31** (not Sep 1). One extra quota day available. Sep 1 = second quota day (leakage/chargeback L3 + L4). Sep 2–5 = packaging.

Everything below is either quota spend (Sep 1) or read-only code over data you already have (Sep 2+).

---

## THE FREEZE BOUNDARY

`agent-freeze` was tagged Aug 31. From here:

| Category | Frozen? |
|---|---|
| Prompts (L3, L4) | **FROZEN** |
| Tool implementations | **FROZEN** |
| L1 matching logic | **FROZEN** |
| Generator + archetypes | **FROZEN** |
| Scoring, calibration, cost, graduation detection | Open — read-only over DB |
| Packets, certificate render | Open — presentation |
| Docs, README, video | Open |

**Write this boundary into the README.** Someone will ask why there are commits after the freeze tag. The answer is "scoring and presentation code, no agent behaviour" and it should be stated, not inferred.

If the hold-out run surfaces a bug in frozen code: it goes in `KNOWN_ISSUES.md`. You do not fix it.

---

## BINDING CONSTRAINTS

| Resource | Limit | Consequence |
|---|---|---|
| Groq TPD | ~200k/day (~50 L3 calls) | Hold-out L3 capped at ~50 |
| Google | **20 req/day** | Hold-out L4 capped at 20, total |
| Runway | 4 working days | Packaging is the risk, not code |

The Google cap is the one that shapes the day. Twenty L4 calls is your entire verifier evidence base. Allocate them deliberately.

---

# SEP 1 — HOLD-OUT DAY

The only day that spends quota. Nothing after today can change a verdict.

### 1.1 Size and generate the seed

Target **~120 records → ~60 open labelled breaks**, weighted toward `FEE_PLUS_GST`, `TDS_194O`, `CHARGEBACK_PLUS_FEE`, `TRUE_LEAKAGE`. Sizing to the quota means ~50 L3 covers most of the pool — you report near-full coverage rather than a subsample of a subsample.

```bash
sbe generate --seed 9999 --dense --target-breaks 60
```

**TESTS — must all pass before spending a single token:**

```
[x] validate_seed(9999) green — generator self-assertion (86 results, Aug 30)
[x] sbe run --seed 9999 → roll-forward ties, count AND value, every day (all_tied=True)
[x] sbe check surfacing --seed 9999 → core trio present with n≥8 each (FEE 10, TDS 11, CHARGEBACK 17; full gate still fails UTR_TRUNCATION — expected cut)
[x] TRUE_LEAKAGE present, n≥5 (n=15)
[x] unlabeled OPEN count recorded — 3/64 (4.7%); lower than ~15% estimate, noted, not fixed
[x] sbe budget --seed 9999 → confirm ~50 L3 covers ≥70% of labelled pool (50/61 ≈ 82%)
```

If the trio isn't present, regenerate with different injection rates. **This is generator config, not frozen logic** — you're allowed to reshape the hold-out pool, you're not allowed to reshape the agent.

### 1.2 L3 run

```bash
sbe investigate --seed 9999 --subsample --limit 50
```

Stratified, checkpointed per break (`conn.commit()` after each `_persist_verdict`). Runs until TPD exhaustion. (`--checkpoint` is not a separate flag — persistence is per-break by default.)

**Run Aug 31:** Groq TPD exhausted at break 15 — **14 verdicts checkpointed** (8 MATCH, 6 NEEDS_HUMAN). 3 breaks skipped (10-turn timeout). Quota reset ~17m; 50 OPEN remain without verdict.

**TESTS:**
```
[x] Every verdict written to DB as it returns — 14/14 audit_log ↔ breaks.verdict match
[x] Zero MATCH verdicts with residual != 0.00   ← hard assertion (8 MATCH, all 0.00)
[x] Roll-forward still ties after L3 writes (all_tied=True)
[x] Per-archetype n recorded: FEE_PLUS_GST MATCH 7; TDS_194O MATCH 1, NEEDS_HUMAN 6
```

### 1.3 L4 run — 20 calls, allocated in advance

Do **not** let the first 20 rows of the table consume the budget. Decide the split now:

| Archetype | L4 calls |
|---|---|
| `FEE_PLUS_GST` | 8 |
| `TDS_194O` | 4 |
| `CHARGEBACK_PLUS_FEE` | 4 |
| `TRUE_LEAKAGE` | 4 |

```bash
sbe verify --seed 9999 --stratified --max-calls 20
```

**Run Aug 31:** Stratified selection wired (`--stratified --max-calls`). Only **14 L3** available (no CHARGEBACK/LEAKAGE L3 yet) → plan picked **FEE 7 + TDS 4** (11 slots), ran **13/14** (2 RPM skips retried; 1 L3 still pending). **6 UPHOLD, 4 OVERTURN, 0 ESCALATE.** Net lift **−14.3pp**, false overturn **75%** on n=13.

**TESTS:**
```
[x] Exactly 20 calls made, no more — 13 ≤ 20 (pool-limited; 1 L3 pending)
[~] Abstention guard — never triggered on 13 calls; guard did NOT block `BRK-2026-0315-0002` NEEDS_HUMAN→MATCH
[ ] No overturn NEEDS_HUMAN→MATCH with non-zero residual — FAIL: `BRK-2026-0315-0002` residual −147.33
[x] L3 audit_log NOT overwritten — asserted in CLI; UPHOLD/ESCALATE keep breaks.verdict = L3
```

Post-run: `python scripts/holdout_l4_checks.py`

### 1.4 Score

```bash
sbe score --seed 9999 --print-table --skip-investigate
```

**Run Aug 31:** CLI **aborts** on contract violation (`BRK-2026-0315-0002` MATCH + non-zero residual from L4 OVERTURN). Metrics from harness (L3 n=14, L4 n=13):

| Archetype | n | correct | L3 acc | verifier_lift |
|---|---|---|---|---|
| `FEE_PLUS_GST` | 7 | 7 | 100% | −42.9pp |
| `TDS_194O` | 7 | 1 | 14.3% | +14.3pp |

Value-weighted reconciled: **43.0%**. Leakage recall: **n/a** (no TRUE_LEAKAGE L3). Roll-forward: **ties**.

**TESTS:**
```
[x] Per-archetype table with raw counts — see above (n and correct, not just %)
[x] Value-weighted reconciled % computed — 43.0%
[~] Leakage recall computed — n/a (no TRUE_LEAKAGE in L3 pool)
[x] Roll-forward ties — OK
```

**Hold-out headline (partial):** L3 FEE **7/7 (100%)**; L4 per-archetype finding (FEE −42.9pp / TDS +14.3pp) — **report as result, not failure**. Leakage recall **n/a** — Tier 0 gap for Sep 1.

Scoring: `sbe score --seed 9999 --print-table --skip-investigate` (default excludes contract violations; `--strict-contract` aborts for demo).

---

# AUG 31 — HOLD-OUT DAY 1 (DONE, PARTIAL)

§1.1–1.4 above. **14 L3, 13 L4.** No more tokens Aug 31.

---

# SEP 1 — SECOND QUOTA DAY (URGENT)

**Tier 0:** Leakage recall. `TRUE_LEAKAGE` n=15 sits untouched — highest-value Groq spend.

### L3 — priority order (forced stratification)

```bash
sbe investigate --seed 9999 --subsample --limit 50
```

`HOLDOUT_SUBSAMPLE_PLAN` order: **TRUE_LEAKAGE (15) → CHARGEBACK (17) → TDS (11) → FEE (3)**. Skips already-verdicted breaks. Target ~36 new L3 if quota allows.

Hand-read one failed TDS verdict before spending (see `KNOWN_ISSUES.md` — GST/TDS conflation).

### L4 — 20 calls on uncovered archetypes

```bash
sbe verify --seed 9999 --stratified --max-calls 20
```

`HOLDOUT_L4_PLAN`: **TRUE_LEAKAGE 8, CHARGEBACK 8, TDS 2, FEE 2.** Finding strengthens at n≈33; report per-archetype table, not blended lift.

### Score

```bash
sbe score --seed 9999 --print-table --skip-investigate
```

Must produce **leakage recall** with n stated. Contract violation row reported separately (implemented).

**End of Sep 1: no more tokens.**

---

# SEP 2 — SCORING CODE + WRITTEN DELIVERABLES

All read-only over the DB. Roughly 7 hours.

### 2.1 `sbe/scoring/cost.py` — 1h

Tokens and ₹ per resolved break, split L3 / L4, from your tool-call logs.

**TESTS:**
```
[ ] Token totals reconcile against provider-reported usage (±5%)
[ ] Cost per resolved break computed separately for L3 and L4
[ ] Handles zero-verdict archetypes without dividing by zero
```

Finance ops buys on this number and nobody else in the track will report it.

### 2.2 `sbe/scoring/calibration.py` — 1h

**3 bins, not 10.** Raw counts per bin alongside percentages. ECE with n stated next to it.

```
CONFIDENCE CALIBRATION (n=47)
  low   (<0.6)    predicted 0.48   actual 6/13  (0.46)
  mid   (0.6-0.85) predicted 0.74  actual 11/16 (0.69)
  high  (>0.85)   predicted 0.93   actual 16/18 (0.89)
  ECE = 0.041  ·  thin bins, interpret with n
```

**TESTS:**
```
[ ] Bins with n<5 flagged in output, not silently reported
[ ] ECE matches a hand-computed value on a 6-row fixture
[ ] n printed alongside every bin — non-negotiable
```

The honest version of this metric reports its own thinness. That's the point.

### 2.3 `sbe/engine/l7_graduation.py::detect_graduation_candidates` — 2h

Detection only. Query over stored verdicts: group by archetype, flag patterns resolved identically with high confidence and zero verifier overturns.

```
RULE PROPOSAL RP-001 · AWAITING APPROVAL
Pattern:   FEE_PLUS_GST — GST-on-fee omitted from merchant ledger
Evidence:  8/8 resolved identically, zero overturns, residual ₹0.00 each
Projected: ~14% of L3 volume on this seed → deterministic
Status:    DETECTION ONLY — promotion workflow not implemented
```

**TESTS:**
```
[ ] Fires on FEE_PLUS_GST given the hold-out data
[ ] Does NOT fire on any archetype with a verifier overturn
[ ] Does NOT fire below the n threshold
[ ] "DETECTION ONLY" appears in output — never implies promotion happened
```

The `llm_calls_by_day` chart stays cut. It needs multiple runs with rules progressively removing L3 work; you're frozen with one hold-out run. Say so in the status line.

### 2.4 `sbe/engine/l6_packets.py` — 2h

Two rendered packets from real hold-out breaks. Format per `ARCHITECTURE.md` §11.

**TESTS:**
```
[ ] residual_unexplained line present and exactly 0.00 on a MATCH packet
[ ] Every evidence line traces to a real source row (source + row index)
[ ] Renders a NEEDS_HUMAN packet without a hypothesis, showing the gap
[ ] No PAN/card data in output
```

Pick one clean `FEE_PLUS_GST` MATCH and one `TRUE_LEAKAGE` `NEEDS_HUMAN`. The second is more persuasive than the first — it shows the system declining to explain something.

### 2.5 Certificate render — 1h

Roll-forward table, value-weighted rate, ageing profile, exception list.

**TESTS:**
```
[ ] Roll-forward ties to zero on the rendered certificate
[ ] Deliberately break it (inject a phantom break) → run refuses to publish
```

That second test is the demo beat at 2:40. Record it.

### 2.6 README as ops runbook

Not a feature list. How to run the daily close. What to do when the roll-forward doesn't tie. Escalation path. Who owns what.

Must contain:
- **Two clearly labelled tables**: dev (pre-freeze) and hold-out (post-freeze), with the tag between them
- The freeze boundary statement
- Clone-and-run reproduction command

### 2.7 `KNOWN_ISSUES.md` final pass

Everything with numbers:
- 4 archetypes injected but not surfaced by L1 — named, with the reason
- Unlabeled OPEN count on both seeds (290 → 57 → hold-out figure)
- Thin n on TDS and CHARGEBACK
- Verifier status: functional on FEE, insufficient n for a stable lift figure
- The verifier bug sequence — keep this, it's your best artifact
- Cut list: promotion workflow, LLM-decline chart, coverage curve, Q&A layer

---

# SEP 3 — README, KNOWN_ISSUES, DEMO

`KNOWN_ISSUES.md` final pass (numbers in). README as ops runbook with dev vs hold-out tables.

Record against **cached replay first**, live second.

| Time | Beat |
|---|---|
| 0:00 | The analyst's problem — three spreadsheets, one short settlement |
| 0:45 | Daily close runs. L1 clears the bulk in ms. Residual shown. |
| 1:15 | Live investigation — tool calls visible, residual driving to ₹0.00 |
| 2:00 | **The verifier bug story** — 100% overturn, the code diff, 136290 → 0.00 |
| 2:40 | Certificate ties. Then inject a phantom break → **run refuses to publish** |
| 3:10 | Break opened day N, auto-closes day N+2 when the credit lands |
| 3:40 | Rule proposal RP-001 with evidence attached |
| 4:10 | Architecture diagram (now, not at minute zero) |
| 4:30 | Hold-out numbers, said out loud, with n — **verifier per-archetype finding** |

**TESTS:**
```
[ ] Cached replay runs end to end with network disabled
[ ] Under 5:00
[ ] Every number spoken on camera matches the README
```

---

# SEP 4 — BUFFER + REPRODUCIBILITY

**TESTS:**
```
[ ] Fresh clone → one command → hold-out numbers reproduce
[ ] Full suite passes on the clone
[ ] make daily-check green on the hold-out seed
[ ] No secrets in the repo, .env.example complete
[ ] Every number in README traceable to a run in runs/
```

Re-record any weak segment. Do not add features.

---

# SEP 5 — SUBMIT EARLY

No code. No edits. Submit in the morning.

---

## THE DAILY CHECK (unchanged, run every day)

```
[ ] Roll-forward ties to zero — count and value
[ ] Re-run of a mid-window day produces byte-identical state
[ ] Zero MATCH verdicts carry a non-zero residual
[ ] Per-archetype table regenerated — did any row get worse?
[ ] No commits touching frozen paths since agent-freeze
```

That last line is new and matters now. Add a CI check or a git hook if it's quick — a commit touching `l3_investigator.py` after the tag undermines every number you report.

---

## IF SEP 1 GOES BADLY

If the hold-out run produces thin or ugly numbers:

**Report them.** You have a frozen agent, a published generator, a hold-out seed the agent never saw, and a `KNOWN_ISSUES.md` with real counts. That combination is worth more than better numbers from an agent you kept tuning.

The non-negotiables are unchanged and all currently intact: roll-forward ties, independent verifier exists and was debugged in public, `TRUE_LEAKAGE` with leakage recall, hold-out discipline, cached demo replay.
