# Settlement Break Engine (SBE)

Ops runbook for the daily settlement close — not a feature list.

An LLM investigator under an independent LLM auditor, gated by a roll-forward
that must tie to zero or the run refuses to publish. Built for Razorpay AI
Buildathon, Track 04 (AI Finance Controller).

Read: `docs/ARCHITECTURE.md` → `docs/BUILD_PLAN.md` → `docs/FINAL_PLAN.md` →
`docs/KNOWN_ISSUES.md`.

---

## Freeze boundary

| Frozen | Open |
|---|---|
| L3 / L4 prompts | Scoring, calibration, cost |
| Tool implementations | Packets / certificate render |
| L1 matching | Docs, README, video |
| Generator archetype *implementations* | Hold-out pool sizing (done) |

**Freeze provenance.** `agent-freeze` (`4c5a0ac`) marks the initial tag;
`behaviour-freeze` (`d3594e2`) is the operative one — prompts, tools, L1 matching
logic, and the generator are unchanged from that commit forward. Verify with:

```bash
git diff behaviour-freeze HEAD -- \
  sbe/engine/l1_deterministic.py \
  sbe/engine/l3_investigator.py \
  sbe/engine/l4_verifier.py \
  sbe/tools/ \
  generator/
```

Post-freeze commits cover quota operations (Groq key rotation in
`l3_investigator.py` — credential selection only; it does not change reasoning),
scoring, and presentation. The hold-out seed 9999 was generated after the freeze
and the agent never saw it during development.

If hold-out surfaces a frozen-path bug → `docs/KNOWN_ISSUES.md`. Do **not** patch.

---

## Clone and reproduce hold-out numbers

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env   # fill INVESTIGATOR_* / VERIFIER_* / INVESTIGATOR_KEY_2

# Seed is local (gitignored under sbe/generator/seeds/). If missing:
sbe generate --seed 9999 --dense --target-breaks 60
sbe run --seed 9999

# Score from existing DB (no API) — primary repro for submission tables:
sbe score --seed 9999 --print-table --skip-investigate
sbe cost --seed 9999
sbe calibrate --seed 9999
sbe graduate --seed 9999
sbe check rollforward --seed 9999
```

Hold-out L3/L4 already live in `runs/sbe_9999.db` for this repo checkout.
Re-running `investigate` / `verify` spends quota and is **not** required to
reproduce the tables.

---

## Daily close

```bash
sbe run --seed <seed>
```

If the roll-forward does not tie, the run raises `ROLL_FORWARD_BREAK` with exact
opening/new/resolved/written-off/closing figures. **Do not silence this.**

```bash
sbe certificate --seed 9999 --date 2026-03-19
sbe certificate --seed 9999 --date 2026-03-19 --phantom   # demo: PUBLISH REFUSED
```

---

## Escalation path

1. Roll-forward doesn't tie → check L2 idempotency / late-arrival before agents.
2. Verifier net lift ≈ 0 or negative → confirm different model family + raw rows
   (see verifier bug sequence in `KNOWN_ISSUES.md`).
3. MATCH with residual ≠ 0.00 → contract violation; default `sbe score` excludes
   it and prints the break ID (`--strict-contract` aborts for demos).
4. Quota death mid-run → L3 checkpoints per break; rotate `INVESTIGATOR_KEY_2`
   then Google `INVESTIGATOR_FALLBACK_*`.

---

## Results — two tables (do not mix)

### Dev (pre-freeze) — seed 2001

| Archetype | n | L3 acc | Notes |
|---|---|---|---|
| `FEE_PLUS_GST` | **8** | **100%** | Headline pre-freeze |
| `CHARGEBACK_PLUS_FEE` | 2 | 50% | Thin n |
| `ADVERSARIAL_NARRATION` | 2 | 50% resisted injection | Trust boundary |
| `TDS_194O` | 1–3 | weak | GST/TDS conflation |

Tag boundary sits between this table and the next.

### Hold-out (post-freeze) — seed 9999

| Archetype | n | correct | L3 acc | verifier_lift |
|---|---|---|---|---|
| `FEE_PLUS_GST` | 7 | 7 | **100%** | −42.9pp |
| `TRUE_LEAKAGE` | 15 | 11 | **73.3%** | +0.0pp |
| `CHARGEBACK_PLUS_FEE` | 13 | 4 | 30.8% | −15.4pp |
| `TDS_194O` | 8 | 1 | 12.5% | +0.0pp |

- **Leakage recall: 73.3% (11/15)**
- Net verifier lift: **−11.6pp** (false overturn 71.4%) — report as finding:
  helps where L3 is weak, hurts where L3 is strong
- L3 total 44 · L4 cumulative 30 · roll-forward ties
- Cost estimate: `sbe cost --seed 9999` (~INR 13.3 at list rates; estimate basis printed)

---

## Packets / graduation / calibration

```bash
sbe packet BRK-2026-0313-0005 --seed 9999          # FEE MATCH sample
sbe packet BRK-2026-0317-0003 --seed 9999          # TRUE_LEAKAGE NEEDS_HUMAN
sbe calibrate --seed 9999
sbe graduate --seed 9999                           # DETECTION ONLY
```

Rendered copies: `runs/9999/packets/`. `llm_calls_by_day` chart is **CUT**
(needs multi-run progression; one frozen hold-out).

---

## Daily check

```bash
make daily-check
# or: sbe check rollforward|surfacing|residuals|l3-landed|l4-plan --seed 9999
```

## Known limitations

See `docs/KNOWN_ISSUES.md` — real per-archetype numbers, verifier bug sequence,
guard miss, four L1-unsourced archetypes, unlabeled OPEN history.
