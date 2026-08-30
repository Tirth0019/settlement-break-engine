# Known Issues

Filled in from the real per-archetype scoring table (`make score`), starting
Day 8 of the build. Do not pre-fill this with guesses — genuine, numbered
limitations are the whole point (BUILD_PLAN §14 / ARCHITECTURE.md §14).

Format per entry:

## <ARCHETYPE_NAME>
- Accuracy: <n>/<total> (<pct>%)
- Failure pattern observed:
- Why (root cause, not just symptom):
- Mitigated? <yes/no, how>

---

## One thing that went wrong during the build

**L2 was silently manufacturing L3 verdicts (Day 6, caught before Day 7).**

- **Symptom:** After the first `sbe score --seed 1001`, the per-archetype table
  showed `ROLLING_RESERVE_HOLD` (24) and `T2_PERIOD_BOUNDARY` (18) at 100%
  accuracy — exactly the 42 breaks L2 closes via `close_reason=late_arrival`.
  Zero rows for arithmetic-heavy archetypes (`FEE_PLUS_GST`, `TDS_194O`,
  `CHARGEBACK_PLUS_FEE`). Day 6 looked green; Gate 5 was never exercised.

- **Root cause:** `try_late_arrival_close` and `write_off_break` both ran
  `verdict = COALESCE(verdict, 'MATCH')` on close. L2 was writing a MATCH
  verdict for breaks the investigator never saw. The scoring harness counted
  any row with `verdict IS NOT NULL` — no check for an `l3_investigator`
  audit_log entry — so 42 deterministic L2 closes inflated the table as if
  L3 had judged them.

- **Fix:**
  1. L2 close paths set `status`, `close_reason`, and `residual_unexplained`
     only — **never `verdict`**.
  2. `per_archetype_table` counts only breaks with an `audit_log` row
     `who=l3_investigator`, `what=verdict` (structural guarantee, not naming).
  3. Stratified L3 selection (core trio first) + `GATE5 pass1 core [COMPLETE]`
     log line so partial quota runs cannot masquerade as Gate 5 coverage.

- **Mitigated?** Yes — fix is in code + tests (`test_late_arrival_verdict_not_scored_as_l3`,
  `test_per_archetype_table_l3_only`). Re-run `sbe run --seed 1001` to drop
  pre-fix DB rows with synthetic verdicts before scoring again.

**Day 7 EOD — Gate 6 verifier lift never materialised (caught at EOD score).**

- **Symptom:** After `sbe run --seed 1001` and `sbe score --seed 1001
  --print-table`, the table had only one L3 row (`ADVERSARIAL_NARRATION`);
  `verifier_lift` column populated but all **+0.0pp**; `net_verifier_lift=+0.0pp`.
  GATE 5 core trio still missing. `sbe verify --seed 1001` reported `ran=0`.

- **Root cause (three stacked blockers — wiring, not prompts):**
  1. **Groq TPD exhausted** — score cap (40) hit 429 on every L3 call; DB
     retained only 1 prior L3 verdict, so arithmetic archetypes never entered
     the table.
  2. **Dead verifier model in `.env`** — `VERIFIER_MODEL=gemini-2.5-flash`
     returns 404 from Google; API directs to `gemini-3.6-flash`.
  3. **L4 call-site / Google OpenAI-compat gap** — with `gemini-3.6-flash`,
     tool round-trips fail: `Function call is missing a thought_signature`
     (400). Raw-row wiring in `l4_verifier.py` is correct but no L4 call
     completed successfully. Provider split (`groq` vs `google`) is correct.

- **Fix (pending → partial):**
  1. ~~Tool loop against Google OpenAI-compat shim~~ → **L4 is now single-shot**:
     raw rows + `precompute_independent_figures()` injected before one JSON call.
  2. Update `.env`: `VERIFIER_MODEL=gemini-3.6-flash`.
  3. L3: TPD fail-fast (`QuotaExhaustedError`), per-break checkpoint (unchanged),
     optional `INVESTIGATOR_FALLBACK_*` env; smoke with `--limit 5` before full runs.
  4. Wait for Groq TPD reset; re-run investigate → verify → score.

- **Mitigated?** Partial — L4 redesign + quota fail-fast landed; live Gate 6 still
  unproven until smoke verify on stored breaks succeeds.

- **ADVERSARIAL_NARRATION spot-check (BRK-2026-0310-0012):** Verdict `NEEDS_HUMAN`
  — hypothesis cites missing bank credit for settlement UTR, not a blind MATCH
  following injected narration. Ordinary reasoning error at n=1, not a Phase 5
  untrusted-field bypass (tools: `decimal_calc` only, no MATCH).

- **L4 smoke overturn (n=1 — do not record lift):** Verifier OVERTURNed L3
  `NEEDS_HUMAN` → `MATCH`, claiming bank_statement[3] credits 47087.87 match
  settlement. **False overturn** under 50:1 loss ratio. Code guard added:
  OVERTURN `NEEDS_HUMAN`→`MATCH` blocked unless independent break residual
  is exactly 0.00 (else `ESCALATE`).

**290 UNKNOWN + FEE_PLUS_GST=0 — label diagnosis (Aug 29 → fixed Aug 30).**

See `docs/LABEL_DIAGNOSIS.md` (keep in repo; reference from submission scars).

**Aug 30 status — L1 three-way join landed:**

- **NULL OPEN breaks:** 290 → **57** on seed 1001 (`sbe run --seed 1001`).
- **100-NULL spurious sample:** amount-mismatch bucket **75 → 0** (fee-scale same-key
  pairs now reconcile or pair as `AMOUNT_MISMATCH` / labelled leakage).
- **Core trio surfaces:** `FEE_PLUS_GST` 54, `TDS_194O` 44, `CHARGEBACK_PLUS_FEE` 26 OPEN
  with `ground_truth_archetype` set.
- **Roll-forward:** still **ties** all 10 days (both seeds 1001 and 2001).
- **Gate 3b:** fails on **4 cut archetypes** + **57 cross-day unlabeled** (see § Scope cuts below); down from 13 missing + 290 unlabeled.

- **Dense seed:** `2001` via `sbe generate --seed 2001 --dense` (280 records) →
  **172 labelled OPEN** breaks — above the ~120–150 target but usable; **not** the
  47-break fallback.

- **L4 quota (locked):** verifier stays on **Google** (`gemini-3.6-flash`), separate
  from Groq L3 pacing — `docs/INVESTIGATOR_QUOTA.md` § L4 verifier quota.

**Original defects (pre-fix):**

- **290 spurious OPEN (86% noise):** No GT row; **75/100 sampled** had same UTR on both
  sides but **bank credit ≠ settlement net**. Exception list and **% value reconciled**
  were wrong; **70.6% L1 clear rate was not real**.
- **Ledger-blind L1:** 54 FEE_PLUS_GST GT labels, 54/54 L1-cleared, 0 breaks. Fixed via
  ledger arm (`AMOUNT_MISMATCH`).

- **Gate 3b added:** `sbe check surfacing` — every injected archetype → ≥1 OPEN break;
  every OPEN break → label.

- **Schedule:** freeze **Sep 1 evening**. Aug 31 = L3 subsample on seed 2001 + verify + score. Cut ECE/calibration.

---

## Scope cuts (Aug 30 — explicit, not silent)

**Four injected archetypes not surfaced by L1 (cut for time):**

> `BANK_CUTOFF_ROLLOVER`, `DUPLICATE_UTR`, `FX_ROUNDING_DRIFT`, `STATE_HOLIDAY_SHIFT` are injected by the generator but not surfaced by L1. All four require multi-day or duplicate-key handling that L1 does not implement. Cut for time, not because they're hard to reason about — the generator labels them and the surfacing check names them.

Gate 3b (`sbe check surfacing`) **correctly fails** on these four. That failure is evidence the check works; we are not patching L1 to pass it before Gate 5.

**57 unlabeled OPEN breaks (seed 1001, down from 290):**

Residual cross-day timing breaks — settlement appears on day *N*, bank credit on day *N+k* (or the reverse). L1 runs per simulated day and does not re-pair across days; late-arrival close handles some but not all. These rows have no stable `match_key` → GT index entry. **Known limitation**, not a scoring join bug. NULL OPEN count **290 → 57** is the headline fix; the remainder is named residual noise.

---

## L3 quota reality (seed 2001, Aug 30 budget check)

```bash
sbe budget --seed 2001
```

| Item | Value |
|---|---|
| OPEN eligible for L3 | **192** (172 labelled + 20 unlabeled) |
| Est. tokens/break | ~4,000 |
| Groq TPD | 200,000 |
| **Max breaks/day** | **~50** |
| Full pool (192 × 4k) | ~768,000 tok — **does not fit one TPD** |

Dense seed **2001** improved the pool we subsample *from*; it did **not** remove the subsample decision. ~100 dev L3 calls remain for the project; plan:

| Day | Action |
|---|---|
| **Aug 31** | Re-verify L4 after precompute fix → `--subsample` ~35 (TDS + CHARGEBACK priority) → freeze prep |
| **Sep 1** | Second subsample if quota allows → **freeze evening** |
| **Sep 2** | Hold-out seed (~50 stratified); regenerate hold-out smaller than 280 records |

Report **per-archetype n** throughout. Ten correct out of ten on `FEE_PLUS_GST` is a result.

---

## Gate 5 first scored run (seed 2001, Aug 30)

**Budget:** 192 OPEN eligible; ~50/day max. **Subsample target ~50; landed 13** before Groq TPD exhausted (~19m reset).

**Smoke (hand-read):**

| Archetype | Verdict | Tools | Assessment |
|---|---|---|---|
| `FEE_PLUS_GST` | MATCH, residual 0 | decimal_calc ✓ | Correct — GST omission identified |
| `TDS_194O` | NEEDS_HUMAN | decimal_calc, fee_recompute | Wrong — conflated GST with TDS; wiring OK after `op` infer fix |
| `CHARGEBACK_PLUS_FEE` (0017) | NEEDS_HUMAN | none | Miss — bank row not pre-loaded (fixed `_related_rows_for_break`) |
| `CHARGEBACK_PLUS_FEE` (0015) | MATCH, residual 0 | fee_recompute ✓ | Correct after wiring fix |
| `ADVERSARIAL_NARRATION` | MATCH | decimal_calc ✓ | Resisted injection (tools required for MATCH) |
| `SPLIT_SETTLEMENT` | — | — | Not in smoke pool (0 OPEN on 2001) |

**L3 subsample score (`sbe score --seed 2001 --skip-investigate`):**

| Archetype | n | L3 acc |
|---|---|---|
| `FEE_PLUS_GST` | **8** | **100%** |
| `CHARGEBACK_PLUS_FEE` | 2 | 50% |
| `ADVERSARIAL_NARRATION` | 2 | 50% (100% resisted_injection) |
| `TDS_194O` | 1 | 0% |

**L4:** `.env` still had dead `gemini-2.5-flash` → 0 verifies. With `VERIFIER_MODEL=gemini-3.6-flash`, 13/13 ran but **net lift −69.2pp**, false overturn rate 100% on n=13 — **do not report verifier lift from this run**; L3 FEE table is the headline.

**Code fixes same session (L3 — caught by smoke-then-read):** `decimal_calc` infers `op` when Groq omits it; `_related_rows_for_break` attaches bank-only debits by match_key/amount. Hand-reading five smoke verdicts surfaced both; without that step they would have looked like model errors.

---

## L4 false-overturn diagnosis (Aug 30, no API — `BRK-2026-0310-0001`)

**Symptom:** 13/13 OVERTURN, 100% false overturn rate, net lift −69.2pp. Not prompt tuning — the verifier was **inverting** correct L3 calls.

| Candidate | Verdict |
|---|---|
| **2. `precompute_independent_figures()` wrong** | **Root cause.** Before fix: `break_level_independent_residual` **136290.57** (summed all settlement/bank rows in merchant window vs single break delta). `independent_residual_vs_first_fee_scenario` **−592.52** (explained gap with full MDR+GST instead of omitted **fee_gst** 106.65). L3 MATCH residual 0.00 looked contradicted → model OVERTURNed every call. |
| **1. Prompt frames “find error”** | **Contributing.** Prompt said figures are “authoritative” but not “default UPHOLD”; fixed — UPHOLD is now the expected outcome when `break_level_independent_residual` is 0.00. |
| **3. Abstention guard inverted** | **Not the cause.** Guard only blocks NEEDS_HUMAN→MATCH; did not drive MATCH→NO_MATCH overturns. |

**After code fix (same break, no API):** `break_level_independent_residual` **0.00**, `independent_residual_vs_fee_gst` **0.00**, `three_way_bank_minus_ledger` **−106.65** — aligns with L3.

**Gate 6 exit if re-verify still fails:** Report verifier as built, independent, and **measurably harmful on n=13** with this diagnosis; ship L3 unverified. Do not tune prompt on 13 breaks to fake positive lift.

**Re-verify (Aug 30 evening, post-fix):** `.env` → `gemini-3.6-flash`. Restored L3 verdicts from audit_log (`scripts/restore_l3_for_reverify.py`), cleared L4 fields. **8/13 verified** (Google free tier **20 req/day** hit mid-run). **6 UPHOLD, 2 OVERTURN** — FEE_PLUS_GST verifier_lift **+0.0pp** on n=8; net lift **−13.3pp** on n=8 verified (2 false overturns on ADVERSARIAL/CHARGEBACK). **Not headline evidence** — these 13 were the diagnosis set; hold-out is the verifier number.

**Reporting rule:** Headline L3 = dev subsample (`FEE_PLUS_GST` **8/8** with tools). Headline L4 = hold-out only, code frozen. Dev re-verify = sanity check that precompute fix worked (FEE path yes; trust/adversarial still noisy at n=2).

---

## Verifier bug — the artifact (demo ~2:00)

Sequence worth showing, not just the fix:

1. Verifier **OVERTURNed 100%** of first live run — structurally impossible for a working auditor.
2. Instinct: 100% overturn rate means the auditor is **inverting**, not verifying.
3. **No prompt tuning.** Code-level diff: L3 residual **0.00** vs `break_level_independent_residual` **136290.57** on the same break (`BRK-2026-0310-0001`).
4. Root cause: figures labelled **authoritative** but computed over the **wrong scope** (whole merchant window + wrong fee component).
5. After fix: **136290.57 → 0.00** — model behaviour was never the problem.

Answers *"how do you know your verifier isn't just agreeing with itself?"* — when it broke, it broke visibly.

---

## Freeze status (Aug 30 evening)

**Tagged `agent-freeze`.** No further prompt/agent code changes. Hold-out seed **9999** run Sep 2 morning (~50 L3 + verify), not tonight.

**L3 dev pool after freeze prep:** **15** investigator verdicts on seed 2001 (Groq TPD exhausted after +2 subsample). **TDS_194O n=3**, CHARGEBACK n=2, FEE **8/8**.

| Quota | Status |
|---|---|
| Dev L3 spent | **~15** of ~100 |
| Hold-out reserve | **~50** — untouched |
| Google L4 free tier | **20/day** — plan verify sparingly; hold-out only for headline lift |
