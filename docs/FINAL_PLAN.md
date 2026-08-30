# SBE — Final Execution Plan (Sep 1 → Sep 5)

Supersedes the phase roadmap in `BUILD_PLAN.md` Part IV. That plan assumed build time was the constraint. It isn't — **quota is**, and the agent is already frozen.

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
[ ] validate_seed(9999) green — generator self-assertion
[ ] sbe run --seed 9999 → roll-forward ties, count AND value, every day
[ ] sbe check surfacing --seed 9999 → core trio present with n≥8 each
[ ] TRUE_LEAKAGE present, n≥5
[ ] unlabeled OPEN count recorded (expected ~15%, note it, don't fix it)
[ ] sbe budget --seed 9999 → confirm ~50 L3 covers ≥70% of labelled pool
```

If the trio isn't present, regenerate with different injection rates. **This is generator config, not frozen logic** — you're allowed to reshape the hold-out pool, you're not allowed to reshape the agent.

### 1.2 L3 run

```bash
sbe investigate --seed 9999 --subsample --checkpoint
```

Stratified, checkpointed per break. Runs until TPD exhaustion.

**TESTS:**
```
[ ] Every verdict written to DB as it returns (kill mid-run, verify persistence)
[ ] Zero MATCH verdicts with residual != 0.00   ← hard assertion
[ ] Roll-forward still ties after L3 writes
[ ] Per-archetype n recorded before moving on
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

**TESTS:**
```
[ ] Exactly 20 calls made, no more
[ ] Abstention guard fires at least once OR is confirmed never triggered
[ ] No overturn NEEDS_HUMAN→MATCH with non-zero residual
[ ] L3 verdicts NOT overwritten — L4 writes to its own column
```

That last one bit you on Aug 31. Assert it.

### 1.4 Score

```bash
sbe score --seed 9999 --print-table --skip-investigate
```

**TESTS:**
```
[ ] Per-archetype table with raw counts (n and correct, not just %)
[ ] Value-weighted reconciled % computed
[ ] Leakage recall computed
[ ] Roll-forward ties
```

**End of day: no more tokens get spent. Write the numbers down.**

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

# SEP 3 — DEMO

Record against the **cached replay first**, live second. A five-minute pitch that dies on an API timeout scores zero regardless of architecture.

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
| 4:30 | Hold-out numbers, said out loud, with n |

**TESTS:**
```
[ ] Cached replay runs end to end with network disabled
[ ] Under 5:00
[ ] Every number spoken on camera matches the README
```

The verifier segment is stronger as a bug story than as a clean overturn. It answers the sharpest question a judge can ask — *how do you know your verifier isn't agreeing with itself?* — with: when it broke, it broke visibly, and we caught it by diffing two computed figures before touching a prompt.

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
