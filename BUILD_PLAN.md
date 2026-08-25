# SBE — Locked Scope & Build Roadmap

Companion to `ARCHITECTURE.md`. That document says *what* the system is. This one says *what is frozen*, *what order it gets built*, and *what gets cut when time runs short*.

Read the Locked Decisions section once. Do not reopen those questions mid-build — every hour spent relitigating a locked decision is an hour not spent on the roll-forward.

---

## PART I — THE LOCKED IDEA

### One paragraph

**Settlement Break Engine (SBE)** runs a payment settlement daily close across three synthetic sources (bank statement, PSP settlement report, merchant ledger). A deterministic pass clears the bulk in milliseconds. Every remaining break enters a persistent break ledger where it gets an ID, ages across runs, and closes when late money arrives. An LLM investigator works each open break with deterministic tools — fee recomputation, banking calendar, subset-sum, identifier normalisation — and must drive `residual_unexplained` to ₹0.00 or abstain. An independent LLM auditor from a different model family, given the raw source rows rather than the investigator's narrative, upholds or overturns each verdict. Every run emits a Reconciliation Certificate whose roll-forward must tie to zero in both count and rupees, or the run refuses to publish. Journal entries are proposed, never posted — maker-checker throughout.

### The thesis, in one line

Reconciliation is not a matching problem. It is a money-movement state machine run daily, and the control that matters is whether the roll-forward ties.

### The three numbers the project lives or dies on

1. **% of settled value reconciled** (not count — count is a vanity metric)
2. **Net accuracy lift from the verifier** (investigator-alone vs post-verifier, plus false-overturn rate)
3. **Leakage recall** — % of `TRUE_LEAKAGE` breaks that correctly survived to `NEEDS_HUMAN`

All three reported from a hold-out seed generated after the agent was frozen.

---

## PART II — LOCKED DECISIONS

Frozen. Changing any of these mid-build invalidates work downstream.

| # | Decision | Value | Why it's locked |
|---|---|---|---|
| L1 | Record count | **1,000** (dev seeds), 1,000 (hold-out) | Below ~800 the hard-case sample can't support any accuracy claim |
| L2 | Investigator model | *Decide today. Write it here.* | — |
| L3 | Verifier model | *Different family. Decide today. Write it here.* | Swapping late invalidates calibration, false-overturn rate, and the hold-out headline |
| L4 | Verifier input | Raw source rows + investigator verdict | Narrative-only input means it can only critique the narrative |
| L5 | Temperature | 0 for both agents | Variance runs are a metric, not an accident |
| L6 | Arithmetic | Only via `fee_recompute` / `decimal_calc` | Silent token-stream maths errors are the top cause of quiet accuracy rot |
| L7 | Materiality | ₹1.00 per break, ₹500/day aggregate cap | Breach raises an exception, never absorbs silently |
| L8 | Loss ratio | 50:1 (false MATCH : false NEEDS_HUMAN) | **Stated policy choice, not empirically optimised** — say this out loud (see R5) |
| L9 | Storage | SQLite, append-only `audit_log` enforced by trigger | Convention-enforced audit logs are not audit logs |
| L10 | Dev seeds | 1001, 1002, 1003 | |
| L11 | Hold-out seed | 9999, generated **after** git tag `agent-freeze` | Pre-empts the "you tuned the data" objection |
| L12 | Name | Settlement Break Engine | Reads like a tool, not a pitch |

**Action before writing any agent code:** fill in L2 and L3, confirm working API access, quota headroom, and acceptable latency for *both* families. "Different model family" is a principle that dies quietly on a rate limit.

---

## PART III — SCOPE TIERS

Build strictly downward. Nothing from a lower tier starts until the tier above it is done and its gate has passed.

### Tier 0 — Non-negotiable trio

Without all three, the project does not clear the track bar.

- Roll-forward that ties to zero, gating publication
- Two-agent loop with a genuinely independent verifier
- `TRUE_LEAKAGE` archetype + leakage recall metric

### Tier 1 — Core

The system is not credible without these.

- Generator with ≥12 archetypes + ground-truth labels + **self-assertion pass**
- Persistent break ledger: stable IDs, ageing buckets, idempotent runs, late-arrival auto-close
- L1 deterministic pass + materiality write-off
- `fee_recompute` and `banking_calendar` tools
- Scoring harness + per-archetype table with raw counts
- Reconciliation Certificate artifact
- Break packets with `residual_unexplained` line

### Tier 2 — What makes it exceptional

Cut only under real time pressure, in this order (last cut first).

1. Calibration: reliability curve + ECE — *keep this; it's ~30 lines against data you already have*
2. Rule graduation **detection** + declining-LLM-calls chart
3. Coverage/accuracy curve
4. Cost per resolved break
5. Run-to-run variance (3 passes)
6. Proposed JEs + maker-checker queue
7. Adversarial narration archetype + trust-boundary slide
8. Archetypes 13–18

### Tier 3 — Stretch

Start only if Tiers 0–2 are complete and tested.

- Rule graduation **promotion** workflow (approval, guards, write-back into L1)
- Settlement Q&A layer — **structured query over verdict records, not RAG**
- Archetypes beyond 18

### Explicitly out of scope

- Vector store / embeddings of any kind
- Real bank or PSP API integration
- Web UI beyond a static certificate render
- Multi-currency beyond the single FX-drift archetype
- Auto-posting journal entries under any circumstance

---

## PART IV — PHASED ROADMAP

Phases are expressed as **% of total available build time**, since the timeline compresses or stretches. Each phase has an **exit gate** — a binary condition. Do not proceed past a red gate; fix it.

---

### PHASE 0 — Foundations · 5% of time

**Goal:** nothing can be built until identifiers, decimals and models are settled.

- Fill in L2 and L3. Smoke-test both APIs end to end.
- Repo scaffold per `ARCHITECTURE.md` §13.
- SQLite schema: `runs`, `breaks`, `audit_log` (+ append-only trigger).
- Decimal discipline: `Decimal` everywhere, never float. One `money.py` module, one rounding policy, used by generator and engine both.
- `fee_schedule.yaml` and `banking_calendar.yaml` — real RBI + state holidays for the simulated window.

**GATE 0:** Both models return a structured response. A test row round-trips through SQLite with exact decimal fidelity. `audit_log` rejects an UPDATE.

---

### PHASE 1 — Generator · 20% of time

**The single highest-leverage phase.** Every downstream number is only as trustworthy as this oracle.

- One module per archetype under `generator/archetypes/`.
- Bank profiles with per-bank narration truncation (16 / 22 / 32 chars).
- Ground-truth labels written to a side table, **stripped from every agent-visible payload**.
- Injection rates configured per archetype; `TRUE_LEAKAGE` at **5–8%**, not 3% (see R5).

**Build the generator's own self-assertion pass.** Before any agent sees the data, an independent checker verifies that every synthetic settlement's arithmetic reconciles to zero, and that the ground-truth label matches what the numbers actually say.

This is the mitigation for the highest-probability silent failure in the whole project: a generator bug is indistinguishable from an agent error, and you will otherwise spend hours tuning a prompt against a broken oracle.

**GATE 1:** Self-assertion pass is green on all three dev seeds. Every archetype appears at its configured rate. Label distribution printed and eyeballed.

---

### PHASE 2 — Break ledger & time · 15% of time

**The hardest engineering in the project.** Not the agents.

- Persistent `break_id` allocation, stable across runs.
- Ageing buckets computed from `first_seen_run`.
- **Idempotency**: re-running a date produces byte-identical state.
- **Late-arrival auto-close**: a break opened Day 1 closes on Day 3 when the T+2 credit lands — without creating a spurious new match.

Everything downstream depends on this: ageing, roll-forward, and rule graduation all break if it's wrong, and it will fail *silently* until the roll-forward stops tying.

**GATE 2:** Run days 1→10 sequentially. Re-run day 5. State is byte-identical. At least one break demonstrably opens on day N and auto-closes on day N+2. Write this as a test, not a manual check.

---

### PHASE 3 — Deterministic pass & tools · 10% of time

Tools exist before the agent that calls them.

- L1 hash-join on canonical identifier.
- Materiality write-off with aggregate cap.
- `fee_recompute` — authoritative, covers fee + GST-on-fee + TDS-on-gross + instant surcharge.
- `banking_calendar` — state-aware settlement-day resolution.
- `normalise_identifier`, `find_split_candidates` (bounded), `decimal_calc`.
- `query_*` tools over the three sources.

**GATE 3:** L1 clear rate lands in 60–75%. `fee_recompute` reproduces every generator-computed fee exactly, for every archetype, to the paise. If it doesn't, one of the two is wrong — find out which before continuing.

---

### PHASE 4 — Roll-forward & scoring harness · 10% of time

Build the control and the measurement **before** the intelligence. Both will catch your own bugs for the rest of the build.

- Roll-forward computation, count and value, gating publication.
- `ROLL_FORWARD_BREAK` exception path.
- Reconciliation Certificate renderer.
- Scoring harness: per-archetype table with raw counts, value-weighted rate, ageing profile, leakage recall.

**GATE 4:** With L1 only and no agents, the roll-forward ties to zero across a 10-day run. The certificate renders. The scoring harness produces a table (mostly `NEEDS_HUMAN` at this stage — that's correct).

---

### PHASE 5 — Investigator · 15% of time

- Structured output: verdict enum, hypothesis, evidence array, `residual_unexplained`, confidence.
- Hard constraint: `MATCH` requires `residual_unexplained == 0.00`.
- Untrusted fields delimited and labelled in-prompt from the very first version — not retrofitted.
- Tool-call logging for the cost metric and the demo.

**GATE 5:** Investigator beats a naive baseline on the per-archetype table, and does so on the *arithmetic-heavy* archetypes specifically (fee+GST, TDS, chargeback). Roll-forward still ties. Zero `MATCH` verdicts with non-zero residual.

---

### PHASE 6 — Verifier · 10% of time

- Different model family (L3). Raw source rows (L4).
- Independently re-runs `fee_recompute` rather than trusting the reported figure.
- Output: `UPHOLD | OVERTURN(new_verdict, reason) | ESCALATE`.

**GATE 6:** Net accuracy lift is **positive**, and false-overturn rate is measured and reported. If lift is ~0, the verifier is rubber-stamping — check it's actually receiving raw rows and actually a different family before touching prompts.

---

### PHASE 7 — Tier 2 features · 10% of time

In the Tier 2 order. Realistically you get through 4–6 of the 8. That is fine and expected.

**GATE 7:** Calibration curve exists. Declining-LLM-calls chart exists (detection-only is sufficient). Roll-forward still ties.

---

### PHASE 8 — Freeze, hold-out, deliverables · 5% of time

1. Git tag `agent-freeze`. **No prompt changes after this point.**
2. Generate hold-out seed 9999.
3. Full run. These are the headline numbers.
4. Run 3× for variance.
5. Write `KNOWN_ISSUES.md` from the actual per-archetype table — the weak rows, with numbers.
6. README as ops runbook.
7. Record the demo. **Ship a cached replay alongside the live run.**

**GATE 8:** Hold-out numbers are in the README. A five-minute video exists that survives an API outage.

---

## PART V — RISK REGISTER

| ID | Risk | Signal it's happening | Mitigation |
|---|---|---|---|
| R1 | **Generator bug scored as agent error** | Agent "fails" an archetype consistently with a suspiciously clean off-by-a-fixed-amount pattern | Phase 1 self-assertion pass; Gate 3 cross-check of `fee_recompute` against generator |
| R2 | **Idempotency / late-arrival state machine slips** | Roll-forward stops tying after a re-run; break counts drift | Gate 2 is a written test, not a manual check. Build before agents. |
| R3 | **Verifier rubber-stamps** | Net lift ≈ 0, overturn rate < 2% | Check family and raw-row input *first*, prompts second |
| R4 | **Token-stream arithmetic creeps in** | Residuals that are almost-but-not-quite zero; ₹0.03 gaps | Assert `residual == 0.00` exactly; log every `decimal_calc` call and diff against reported figures |
| R5 | **50:1 loss ratio fitted to single-digit false MATCHes** | Fewer than ~15 false MATCHes in the hard-case set | Raise `TRUE_LEAKAGE` injection to 5–8%. **And state plainly that 50:1 is a policy choice, not an optimisation.** Presenting it as empirically derived when it rests on nine data points is exactly what a sharp judge probes in Q&A. |
| R6 | **Scope creep into Tier 3** | Time spent on Q&A or promotion workflow before Gate 7 | Tier discipline. Q&A is *structured query*, one hour, or nothing. |
| R7 | **Demo dies live** | — | Cached replay, recorded before the deadline, not after |
| R8 | **Model access fails late** | — | Phase 0 smoke test. Have a fallback family identified. |

---

## PART VI — DEFINITION OF DONE

A judge should be able to:

1. Clone the repo, run one command, and reproduce the hold-out numbers.
2. Read `KNOWN_ISSUES.md` and find honest weaknesses with counts attached.
3. Watch a break open on one day and auto-close on another.
4. See the roll-forward tie to zero, and see what happens when it doesn't.
5. See the verifier overturn a wrong call, with a stated reason.
6. See a `TRUE_LEAKAGE` break that the system refused to explain away.
7. Read a break packet and understand exactly where the money went, to the paise.

If all seven are true, the track's bar — *throughput plus measured accuracy plus an honest exception list* — is cleared with room.

---

## PART VII — THE DAILY CHECK

Every day of the build, in order. Three minutes.

```
[ ] Roll-forward ties to zero on the latest 10-day dev run
[ ] Re-run of a mid-window day produces byte-identical state
[ ] fee_recompute matches generator arithmetic on all archetypes
[ ] Zero MATCH verdicts carry a non-zero residual
[ ] Per-archetype table regenerated — did any row get worse?
[ ] Current phase gate: still green?
```

If the first line fails, stop and fix it before anything else. It is the control for a reason.

---

## PART VIII — IF YOU ARE BEHIND

Ordered triage. Give up items top-down.

1. Drop to 12 archetypes — keep `FEE_PLUS_GST`, `TDS_194O`, `CHARGEBACK_PLUS_FEE`, `REFUND_NETTED`, `ROLLING_RESERVE_HOLD`, `SPLIT_SETTLEMENT_N1`, `T2_PERIOD_BOUNDARY`, `STATE_HOLIDAY_SHIFT`, `UTR_TRUNCATION`, `DUPLICATE_UTR`, `TRUE_LEAKAGE`, `ADVERSARIAL_NARRATION`
2. Drop rule-graduation promotion; keep detection + the chart
3. Drop proposed JEs; keep the maker-checker *concept* in the doc and one mock in the video
4. Drop the coverage curve; keep calibration
5. Drop run-to-run variance to 2 passes
6. Reduce the simulated window from 10 days to 6 — **never below 4**, or late-arrival auto-close has nothing to demonstrate

**Never give up:** the roll-forward, the independent verifier, `TRUE_LEAKAGE` + leakage recall, the hold-out seed, or the cached demo replay.
