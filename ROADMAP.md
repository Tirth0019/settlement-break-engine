# Settlement Break Engine — Build Roadmap

**Window:** Aug 24 → Sep 5, 2026 (13 days). Target: submit by Sep 4 EOD, Sep 5 held as pure buffer.

**Sequencing logic:** the generator and the break-ledger state machine are the two things every downstream number depends on, and both are where silent bugs hide longest. They're built and stress-tested before a single LLM call is written. Agents come in the second half, once there's a trustworthy oracle and a trustworthy ledger to point them at.

---

## Day 0 — Aug 24 (today): Lock decisions, not code

Nothing here should still be undecided by tonight — every hour after this assumes these are settled.

- [ ] **Lock the model pair.** Pick investigator model + verifier model (different families). Get API keys for both, run one real tool-calling call against each at your target concurrency, measure actual latency — not docs latency.
- [ ] Confirm quota headroom for ~1,000-3,000 calls per family (320 hard cases × up to 3 passes for variance testing, across dev seeds + hold-out).
- [ ] Write the model choice + why into `README.md` now. Don't revisit.
- [ ] Repo scaffold per the layout in ARCHITECTURE.md §13 — empty files, not empty folders, so imports don't break later.
- [ ] `reference/fee_schedule.yaml` and `reference/banking_calendar.yaml` — real numbers (actual Razorpay-published MDR bands if findable, plausible ones if not; actual RBI + one state holiday calendar for 2026).
- [ ] Decide the tech stack explicitly: Python version, SQLite driver, LLM SDKs, `decimal` (not float) enforced from the first line of code.

**Done when:** both models have answered a real tool call, the repo has every file stubbed, README states the model pair.

---

## Day 1 — Aug 25: Generator core + first 6 archetypes

- [ ] Multi-day seed directory structure (`generator/seeds/<seed>/day_XX/`) — build this shape now, even with one day of data, because everything downstream assumes it exists.
- [ ] `generator/archetypes/` module interface: `generate(rng, merchant, date, fee_schedule, calendar) -> ArchetypeResult` with mandatory `self_check == Decimal("0.00")`.
- [ ] Implement: `FEE_PLUS_GST`, `TDS_194O`, `CHARGEBACK_PLUS_FEE`, `REFUND_NETTED`, `TRUE_LEAKAGE`, `ADVERSARIAL_NARRATION` — the six that carry the most scoring weight and the trust-boundary requirement.
- [ ] Each module's `self_check` reuses the *same* fee math the engine's `fee_recompute` tool will use later (write that shared math module today, both consumers import it — this is what prevents the generator and the engine silently disagreeing).
- [ ] `TRUE_LEAKAGE` injected at 8% (not 3%) per the loss-ratio discussion — write the rationale into `ARCHITECTURE.md` now while it's fresh.

**Done when:** these 6 archetypes generate valid rows for a single day, `self_check` passes for all of them, and you can eyeball a `CHARGEBACK_PLUS_FEE` row and manually verify the arithmetic.

---

## Day 2 — Aug 26: Remaining archetypes + multi-day lifecycle

- [ ] Implement the rest: `ROLLING_RESERVE_HOLD`/`_RELEASE` (explicit `MULTI_DAY` pair), `INSTANT_SETTLEMENT_FEE`, `SPLIT_SETTLEMENT_N1`/`_1N`, `T2_PERIOD_BOUNDARY` (`MULTI_DAY`), `STATE_HOLIDAY_SHIFT`, `BANK_CUTOFF_ROLLOVER`, `UTR_TRUNCATION`, `UPI_RRN_VS_UTR`, `DUPLICATE_UTR`, `FX_ROUNDING_DRIFT`.
- [ ] Wire lifecycle tagging (`SAME_DAY` vs `MULTI_DAY`) into the manifest — `MULTI_DAY` archetypes must reference their originating break across day folders.
- [ ] `validate_seed()` — the generator's own roll-forward: every archetype's `self_check` passes, cross-source totals balance, before any file is written.
- [ ] Generate dev seeds `1001`, `1002`, `1003` at the injection-rate table (~1,000 records, ~30 merchants, 12 dates) spanning at least 10 simulated days each — you need the day-count for the rule-graduation chart later, so don't shortcut to 3-4 days now.

**Done when:** `validate_seed()` passes clean on all three dev seeds, and `manifest.json` correctly shows which breaks are multi-day and when they should close.

---

## Day 3 — Aug 27: Break ledger + idempotency + late-arrival close

**This is the highest-risk day in the whole roadmap — treat it as such, don't compress it.**

- [ ] `L2 break_ledger.py`: persistent `break_id` generation, ageing bucket computation, carry-forward across runs.
- [ ] Idempotency: re-running the same day against the same inputs produces byte-identical `breaks` table state. Write this as an actual test, not a manual check.
- [ ] Late-arrival auto-close: a `MULTI_DAY` credit landing on day N correctly closes the break opened on day 1, without creating a duplicate break.
- [ ] SQLite schema: `runs`, `breaks`, `audit_log` (append-only, enforced by trigger).
- [ ] Run the full 10-day sequence from seed `1001` through the ledger. Assert every `MULTI_DAY` archetype's break opens and closes on the days the manifest says it should.

**Done when:** running seed `1001` twice from scratch gives identical `breaks` table content both times, and at least one `T2_PERIOD_BOUNDARY` and one `ROLLING_RESERVE` break demonstrably opens on day 1 and closes on the correct later day.

---

## Day 4 — Aug 28: Deterministic pass + roll-forward control

- [ ] `L1 l1_deterministic.py`: exact hash-join on canonical identifier, materiality write-off (`|Δ| < ₹1.00`, capped aggregate).
- [ ] `fee_recompute` and `banking_calendar` tools — built now as standalone, tested functions, before any agent calls them.
- [ ] `L5 l5_rollforward.py`: the control — `opening + new − resolved − written_off == closing`, count and ₹, both must tie or the run refuses to publish.
- [ ] Run L1 + L2 + L5 together across all three dev seeds. **Any roll-forward failure here is a generator or ledger bug — find and fix it now, before agents exist to blame.**

**Done when:** all three dev seeds produce a tying roll-forward through L1 alone (open breaks are just the un-cleared residual — no agent verdicts yet), and clear rate lands in the 60-75% target band without being tuned to hit it.

---

## Day 5 — Aug 29: Buffer + scoring harness

Built in deliberately — day 3 or day 4 slipping silently is the single most likely failure mode per the earlier risk discussion.

- [ ] Absorb any overflow from days 1-4.
- [ ] `scoring/harness.py`: joins `ground_truth.jsonl` back against results, produces the per-archetype table shape (n, correct, acc) even with placeholder verdicts, so the harness exists before the agent does.
- [ ] `scoring/cost.py` and `scoring/calibration.py` stubbed with real function signatures (reliability curve, ECE) — implementation comes day 9, but the interface is fixed now.

**Done when:** the harness runs against L1-only output and produces a (mostly empty) per-archetype table without erroring — proves the plumbing works before it has real data to show.

---

## Day 6 — Aug 30: Investigator agent

- [ ] `L3 l3_investigator.py` + `engine/tools/`: `query_ledger`, `query_bank`, `query_settlement`, `find_split_candidates`, `normalise_identifier`, `reserve_schedule`, `decimal_calc` — all deterministic, all logged.
- [ ] Structured output: verdict enum, `hypothesis`, `evidence[]`, `residual_unexplained` (must be `0.00` for any `MATCH`).
- [ ] Trust boundary (§10): untrusted fields delimited and labelled in the prompt, tool outputs never re-interpreted as instructions, verdict constrained to enum (can't be closed by prose). Test directly against your `ADVERSARIAL_NARRATION` rows.
- [ ] Run against open breaks from dev seed `1001`. Don't touch the verifier yet — get investigator-alone accuracy first so day 7's net-lift number means something.

**Done when:** investigator produces evidence-backed verdicts on real open breaks, `residual_unexplained` is genuinely computed (not hardcoded to zero), and it doesn't fall for the adversarial narration row.

---

## Day 7 — Aug 31: Verifier agent

- [ ] `L4 l4_verifier.py`: second model family, sees **raw source rows**, independently re-runs `fee_recompute` rather than trusting the investigator's reported figure.
- [ ] Output: `UPHOLD | OVERTURN(new_verdict, reason) | ESCALATE`.
- [ ] Compute both headline pieces: **net accuracy lift** (investigator-alone vs. post-verifier) and **false-overturn rate**. Do not compute or report raw "overturn rate" as a standalone number.
- [ ] Full L1→L4 pipeline run on dev seed `1001`. First point where the whole per-archetype table has real numbers in every column.

**Done when:** you have a real per-archetype table with n/correct/acc/verifier_lift for dev seed `1001`, and you can state net lift and false-overturn rate as actual numbers, not placeholders.

---

## Day 8 — Sep 1: Break packets, maker-checker, KNOWN_ISSUES

- [ ] `L6`: break packet generation (the copy-pasteable analyst artifact from §11) and proposed JE structure.
- [ ] Maker-checker approval queue — agent proposes, nothing auto-posts, append-only audit log entry per proposal.
- [ ] Start `KNOWN_ISSUES.md` for real, now that you have real per-archetype accuracy — write down the archetypes it's genuinely weak on, with the actual numbers from day 7's run.
- [ ] Note one real bug you hit and fixed today (per §14) — write it down when it happens, don't reconstruct it later for the README.

**Done when:** a break packet reads like something an analyst could paste into an email, and `KNOWN_ISSUES.md` has at least 2-3 entries with real numbers, not placeholders.

---

## Day 9 — Sep 2: Rule graduation (split) + calibration (kept in scope)

- [ ] **Rule graduation — ship the cheap half only:** detection of repeated high-confidence, zero-overturn resolutions per archetype, and the declining-LLM-calls-per-day chart. Stub the approval/promotion-into-L1 workflow — show the proposal, don't wire it back into L1 live.
- [ ] **Calibration — implement fully, not stretch:** reliability curve + ECE from `confidence` vs. `ground_truth`, using the day 7 run's data. This is genuinely ~30 lines against a table you already have.
- [ ] Loss-weighted abstention (§9.3): compute the coverage/accuracy curve at 100/90/80% coverage using the 50:1 ratio, and write the honest caveat into the doc — leakage injected at 8% specifically to make this threshold tunable, stated as a deliberate stress rate, not a claimed real-world base rate.

**Done when:** you have a real reliability curve/ECE number, a real coverage/accuracy curve, and a rule-graduation proposal list with at least one plausible promotion candidate and its projected savings.

---

## Day 10 — Sep 3: Full multi-day dry run + fix pass

- [ ] Run the complete pipeline (L1→L7, minus live rule promotion) across all three dev seeds, full 10-day sequence each.
- [ ] Verify the declining-LLM-calls chart actually declines across the simulated days — if it doesn't, the graduation detection logic needs another look before freeze.
- [ ] Verify at least one visible Day-1-open/Day-3-close break survives end to end through the full pipeline for the demo.
- [ ] Fix whatever the full run surfaces. This is your last day where fixing something doesn't put the hold-out run at risk.

**Done when:** a full L1-L7 run completes clean on all three dev seeds with a tying roll-forward on every simulated day, and you have the specific break IDs you'll use in the demo.

---

## Day 11 — Sep 4: Freeze, hold-out run, video

- [ ] **Freeze:** git-tag the generator and both agent prompts together. No code changes after this point.
- [ ] Generate hold-out seed `9999` — a seed the agent has never seen, generated after freeze.
- [ ] Run the full pipeline once against `9999`. These are your headline numbers. Report them as-is, say on camera that it's a frozen hold-out.
- [ ] Record the demo per the §15 beat sheet (analyst problem → daily close → live investigation → verifier overturn → certificate → Day-3 auto-close → graduation chart → architecture → headline numbers).
- [ ] Record a live take, but also save a cached replay — the fallback if the live run hits an API hiccup during recording or judging.
- [ ] Finish README as an ops runbook (how to run daily close, what to do when roll-forward doesn't tie, escalation path) and finalize `KNOWN_ISSUES.md`.

**Done when:** hold-out numbers are recorded and locked, video is in hand (live + cached backup), README and KNOWN_ISSUES read like practitioner docs, not a feature list.

---

## Day 12 — Sep 5: Submission buffer

- [ ] Final repo read-through as if you're a judge seeing it cold.
- [ ] Public repo, 5-min pitch video, architecture doc — submit.
- [ ] No new features. This day exists only to absorb whatever Day 11 didn't finish.

---

## What to cut first if you fall behind

In order: **Q&A layer** (never build RAG for it if you build it at all) → **rule graduation's promotion mechanic** (keep detection + chart, it's cheap and it's the differentiator) → **archetype count** (12 solid archetypes beats 18 shallow ones — but don't cut `TRUE_LEAKAGE`, `ADVERSARIAL_NARRATION`, or the `MULTI_DAY` pair, since those are what the demo and the trust-boundary story depend on).

**Never cut:** the roll-forward control, idempotency, calibration, the verifier's independent `fee_recompute` re-run, or the hold-out discipline. These are what separate this from every other submission's "matcher with an LLM label on top."
