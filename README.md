# Settlement Break Engine (SBE)

A daily-close reconciliation control system for payment settlements — an LLM
investigator under an independent LLM auditor, gated by a roll-forward that
has to tie to zero. Built for Razorpay AI Buildathon, Track 04 (AI Finance
Controller).

Read in this order: `ARCHITECTURE.md` (what it is) → `BUILD_PLAN.md` (locked
scope, phases, gates, risk register) → `ROADMAP.md` (day-by-day schedule).

## Quickstart

```bash
make setup                 # venv + deps + .env from template
# now fill in .env: INVESTIGATOR_* and VERIFIER_* — see BUILD_PLAN.md L2/L3
make generate               # synthetic seed 1001, 10 simulated days
make validate                # generator self-assertion pass — must be green
make run                     # full L1-L7 pipeline on seed 1001
make score                   # per-archetype table + headline metrics
```

## Daily close — running it for real

```bash
sbe run --seed <seed> --date 2026-03-18
```

If the roll-forward does not tie, the run refuses to publish and prints a
`ROLL_FORWARD_BREAK` exception with the exact opening/new/resolved/written-off
figures. **Do not silence this. Fix the ledger or the generator, in that
order of suspicion — see BUILD_PLAN.md Risk Register R1/R2.**

## Escalation path (finance-ops framing, not a feature list)

1. Roll-forward doesn't tie → check Phase 2 (idempotency/late-arrival) before
   suspecting the agents. It is very rarely the agents.
2. Verifier net lift ≈ 0 → confirm it's actually receiving raw source rows
   and is actually a different model family before touching prompts (R3).
3. Residual not exactly `0.00` → an arithmetic call happened outside
   `fee_recompute`/`decimal_calc`. Grep for raw `Decimal` math in agent code.

## Daily check (run this every day of the build — three minutes)

```bash
make daily-check
```

## Freeze boundary (`agent-freeze`, tagged Aug 31)

Commits after this tag are **scoring and presentation only**. They do not change agent behaviour.

| Frozen after `agent-freeze` | Still open |
|---|---|
| L3 / L4 prompts | Scoring, calibration, cost |
| Tool implementations (`fee_recompute`, `decimal_calc`, query_*) | Packet / certificate render |
| L1 matching logic | Docs, README, video |
| Generator + archetype *implementations* | Hold-out **pool sizing** (injection rates / `--target-breaks`) |

If the hold-out run surfaces a bug in a frozen path, it is recorded in `docs/KNOWN_ISSUES.md`. It is **not** patched.

The published tag `agent-freeze` points at `4c5a0ac` (Day 6). The L1/L3/L4 behaviour actually frozen for scoring is commit `d3594e2`. CI checks frozen files against `d3594e2`, not the earlier tag.

## Freeze & hold-out

```bash
sbe generate --seed 9999 --dense --target-breaks 60
sbe validate --seed 9999
sbe run --seed 9999
sbe investigate --seed 9999 --subsample
sbe verify --seed 9999 --limit 20
sbe score --seed 9999 --skip-investigate --print-table
```

See `docs/FINAL_PLAN.md`. Do not edit `sbe/engine/l3_investigator.py` or `sbe/engine/l4_verifier.py` after the tag.

## Repo layout

See `ARCHITECTURE.md` §13.

## L1 clear rate — why it went *down* (Aug 30)

After the three-way L1 fix on seed 1001:

| Metric | Before (broken L1) | After (correct L1) |
|---|---|---|
| Avg daily clear rate | **70.6%** | **56.7%** |
| NULL OPEN breaks | 290 | 57 |

The drop is **not a regression**. The old number was inflated: L1 falsely cleared ~75 same-key amount mismatches per 100-NULL sample by exact-matching bank credit to settlement net without fee reconciliation or a ledger arm. Those rows were hidden breaks, not clean traffic.

The corrected pass **surfaces** them — via `AMOUNT_MISMATCH` (ledger variance), labelled `TRUE_LEAKAGE`, or residual cross-day sides. A submission that reports its own clear rate going down after a correctness fix is doing something almost nobody does.

See `docs/LABEL_DIAGNOSIS.md` for before/after queries.

## Known limitations

See `KNOWN_ISSUES.md` — filled in with real per-archetype numbers starting
Day 8 of the build (see `ROADMAP.md`), not written in advance.
