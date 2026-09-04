# SBE — Final Execution Plan (Aug 31 hold-out → Sep 5 submit)

Supersedes the phase roadmap in `BUILD_PLAN.md` Part IV. That plan assumed build time was the constraint. It isn't — **quota is**, and the agent is already frozen.

**Timeline revision (Aug 31 evening):** Hold-out ran **Aug 31** (not Sep 1). One extra quota day available. Sep 1 = second quota day (leakage/chargeback L3 + L4). Sep 2–5 = packaging.

Everything below is either quota spend (Sep 1) or read-only code over data you already have (Sep 2+).

---

## THE FREEZE BOUNDARY

`agent-freeze` was tagged Aug 31. From here:| Category | Frozen? |
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

**Run Aug 31 (day 1):** Groq TPD exhausted at break 15 — **14 verdicts** (FEE 7 MATCH; TDS 1 MATCH + 6 NEEDS_HUMAN).

**Run Sep 1–3 (day 2, leakage-first):** **44 L3 total** (audit_log). TRUE_LEAKAGE **15/15**, CHARGEBACK **13**, FEE **7**, TDS **9**. ~20 OPEN remain without L3.

**TESTS:**
```
[x] Every verdict written to DB as it returns — audit_log ↔ L3 map intact
[x] Zero L3 MATCH with residual != 0.00 (L3-only; one L4 OVERTURN contract violation excluded from table)
[x] Roll-forward still ties after L3 writes
[x] Per-archetype n: FEE 7; TDS 9; CHARGEBACK 13; TRUE_LEAKAGE 15
```

### 1.3 L4 run — allocate after L3 lands

```bash
sbe check l4-plan --seed 9999
sbe verify --seed 9999 --stratified --max-calls 20
```

**Final L4 (cumulative, n=30):** TRUE_LEAKAGE 12 (10 UPHOLD / 2 OVERTURN); CHARGEBACK 5 (3/2); FEE 7 (4/3); TDS 6 (5/1). Some skips on Google connection/503 — not all pending verified.

**TESTS:**
```
[x] Cap respected per run (≤20/call batch); cumulative n=30 across days
[~] Abstention guard — never blocked `BRK-2026-0315-0002` (documented KNOWN_ISSUES)
[ ] No overturn NEEDS_HUMAN→MATCH with non-zero residual — FAIL: that break residual −147.33 (excluded from score table)
[x] L3 audit_log NOT overwritten
```

### 1.4 Score

```bash
sbe score --seed 9999 --print-table --skip-investigate
```

**Final hold-out table (Sep 3):**

| Archetype | n | correct | L3 acc | verifier_lift |
|---|---|---|---|---|
| `FEE_PLUS_GST` | 7 | 7 | **100%** | −42.9pp |
| `TRUE_LEAKAGE` | 15 | 11 | **73.3%** | +0.0pp |
| `CHARGEBACK_PLUS_FEE` | 13 | 4 | 30.8% | −15.4pp |
| `TDS_194O` | 8 | 1 | 12.5% | +0.0pp |

- **Leakage recall: 73.3% (11/15)** — Tier 0 closed
- Value-weighted reconciled (post-L4 MATCH): **15.6%**
- Net verifier lift: **−11.6pp**; false overturn rate **71.4%**
- Roll-forward: **ties**
- Contract violation excluded: `BRK-2026-0315-0002`

**TESTS:**
```
[x] Per-archetype table with raw counts
[x] Value-weighted reconciled % computed
[x] Leakage recall computed — 73.3% (n=15)
[x] Roll-forward ties — OK
```

**Hold-out headlines:** L3 FEE **7/7 (100%)**; leakage recall **11/15 (73.3%)**; L4 helps weak L3 / hurts strong L3 (report as finding).

---

# AUG 31 — HOLD-OUT DAY 1 (DONE, PARTIAL)

§1.1–1.4 day-1 partial. **14 L3, 13 L4.**

---

# SEP 1–3 — SECOND QUOTA WINDOW (DONE)

```
[x] L3 leakage-first — TRUE_LEAKAGE 15 + CHARGEBACK 13 landed
[x] sbe check l3-landed / l4-plan
[x] L4 stratified on pending (connection skips noted)
[x] sbe score — leakage_recall=73.3%
```

**No more hold-out tokens.** Packaging only from here.

---

# SEP 2 — SCORING CODE + WRITTEN DELIVERABLES

All read-only over the DB. **Done Sep 3 (packaging day).**

### 2.1 `sbe/scoring/cost.py` — done

```
[x] Token totals from audit call counts × configured tok/call (estimate basis printed)
[x] Cost per resolved break computed separately for L3 and L4
[x] Handles zero-verdict archetypes without dividing by zero
```

`sbe cost --seed 9999` → L3 44 / L4 30 · ~INR 13.3 (list-rate estimate).

### 2.2 `sbe/scoring/calibration.py` — done

```
[x] Bins with n<5 flagged (`[THIN n<5]`)
[x] ECE matches hand-computed 6-row fixture (tests)
[x] n printed alongside every bin
```

Hold-out: n=44, ECE≈0.217, mid thin, high bin overconfident.

### 2.3 `sbe/engine/l7_graduation.py::detect_graduation_candidates` — done

```
[x] Would fire on FEE with zero overturns (unit fixture)
[x] Does NOT fire on any archetype with a verifier overturn (hold-out: none)
[x] Does NOT fire below the n threshold
[x] "DETECTION ONLY" appears in output
```

`llm_calls_by_day` status **CUT** (one frozen hold-out run).

### 2.4 `sbe/engine/l6_packets.py` — done

```
[x] residual_unexplained on MATCH packet
[x] Evidence lines trace to source refs when present
[x] NEEDS_HUMAN packet without hypothesis shows the gap
[x] No PAN/card data in output (masked)
```

Samples: `runs/9999/packets/fee_match_BRK-2026-0313-0005.txt`,
`runs/9999/packets/leakage_needs_human_BRK-2026-0317-0003.txt`.

### 2.5 Certificate render — done

```
[x] Roll-forward ties on rendered certificate
[x] `--phantom` → PUBLISH REFUSED
```

`sbe certificate --seed 9999 --date 2026-03-19`

### 2.6 README as ops runbook — done

Dev vs hold-out tables, freeze boundary, clone-and-run repro.

### 2.7 `KNOWN_ISSUES.md` final pass — done

Numbers, cut list, unlabeled history, verifier finding, guard miss, TDS diagnosis.

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
