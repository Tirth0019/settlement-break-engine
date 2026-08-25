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

## Freeze & hold-out

```bash
make freeze     # tags agent-freeze, generates + runs seed 9999, prints headline numbers
```

No code changes after `make freeze`. See BUILD_PLAN.md Phase 8.

## Repo layout

See `ARCHITECTURE.md` §13.

## Known limitations

See `KNOWN_ISSUES.md` — filled in with real per-archetype numbers starting
Day 8 of the build (see `ROADMAP.md`), not written in advance.
