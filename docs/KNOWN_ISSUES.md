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
