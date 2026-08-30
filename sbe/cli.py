"""
CLI entrypoint — `sbe <command>` (installed via pyproject [project.scripts]).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import typer
from rich import print as rprint

app = typer.Typer(help="Settlement Break Engine")


@app.command()
def generate(seed: str = "1001", days: int = 10, dense: bool = False):
    """Generate a synthetic seed (ROADMAP.md Day 1-2). Use --dense for scoring pool (~450 rows)."""
    from sbe.generator.seed import generate_seed

    out = generate_seed(seed=seed, days=days, dense=dense)
    rprint(f"[green]Generated seed {seed} -> {out}[/green]")


@app.command()
def validate(seed: str = "1001"):
    """Run the generator self-assertion pass (GATE 1)."""
    from sbe.generator.seed import SEEDS_ROOT, load_seed_results_for_validate
    from sbe.generator.validate_seed import validate_seed

    seed_dir = SEEDS_ROOT / seed
    if not seed_dir.exists():
        raise typer.BadParameter(
            f"seed directory missing: {seed_dir} — run `sbe generate --seed {seed}` first"
        )

    results = load_seed_results_for_validate(seed)
    summary = validate_seed(results, print_distribution=True)
    rprint(
        f"[green]GATE 1 OK[/green] - {summary['n']} results, "
        f"labels={len(summary['label_counts'])}"
    )


@app.command()
def run(seed: str = "1001", date: str = None):
    """Run L1+L2+L5 for one day (YYYY-MM-DD) or all days if date omitted."""
    from sbe.config import DB_PATH
    from sbe.db.connection import get_connection
    from sbe.engine.pipeline import run_day, run_seed
    from sbe.generator.seed import SEEDS_ROOT

    if not (SEEDS_ROOT / seed / "manifest.json").exists():
        raise typer.BadParameter(f"seed {seed} missing — run sbe generate first")

    db_path = Path(DB_PATH).parent / f"sbe_{seed}.db"
    if db_path.exists() and date is None:
        db_path.unlink()
    conn = get_connection(str(db_path))

    if date:
        manifest = __import__("json").loads(
            (SEEDS_ROOT / seed / "manifest.json").read_text(encoding="utf-8")
        )
        start = __import__("datetime").date.fromisoformat(manifest["start_date"])
        run_d = __import__("datetime").date.fromisoformat(date)
        day = (run_d - start).days + 1
        if day < 1:
            raise typer.BadParameter(f"date {date} is before seed start {start}")
        result = run_day(conn, seed=seed, day=day)
        rprint(
            f"[green]run OK[/green] seed={seed} day={day} clear_rate="
            f"{result['clear_rate']:.1%} ties={result['certificate']['ties']}"
        )
    else:
        results = run_seed(conn, seed=seed)
        clears = [r["clear_rate"] for r in results]
        avg = sum(clears) / len(clears) if clears else 0
        rprint(
            f"[green]run OK[/green] seed={seed} days={len(results)} "
            f"avg_clear_rate={avg:.1%} all_tied={all(r['certificate']['ties'] for r in results)}"
        )
    conn.close()


@app.command()
def investigate(
    seed: str = "1001",
    limit: int = typer.Option(None, help="Max OPEN breaks (ignored when --smoke)"),
    smoke: bool = typer.Option(
        False,
        "--smoke",
        help="Named smoke slice: one break each from core trio + ADVERSARIAL + SPLIT",
    ),
    subsample: bool = typer.Option(
        False,
        "--subsample",
        help="Quota stratified subsample (fixed n per archetype, default cap 50)",
    ),
    test_fallback: bool = typer.Option(
        False,
        "--test-fallback",
        help="Force dead primary model ID to verify INVESTIGATOR_FALLBACK_* wiring",
    ),
    through_day: int = typer.Option(
        None, "--through-day", help="Run L1+L2+L5 through this day first"
    ),
):
    """Run L3 investigator on OPEN breaks (stratified; L2-resolved breaks skipped)."""
    from sbe.config import DB_PATH, INVESTIGATE_PER_RUN_CAP
    from sbe.db.connection import get_connection
    from sbe.engine.l3_investigator import investigate_open_breaks
    from sbe.engine.pipeline import run_day, run_seed
    from sbe.generator.seed import SEEDS_ROOT

    if not (SEEDS_ROOT / seed / "manifest.json").exists():
        raise typer.BadParameter(f"seed {seed} missing — run sbe generate first")

    db_path = Path(DB_PATH).parent / f"sbe_{seed}.db"
    conn = get_connection(str(db_path))

    if through_day is not None:
        for d in range(1, through_day + 1):
            run_day(conn, seed=seed, day=d)
    elif not db_path.exists() or conn.execute(
        "SELECT COUNT(*) FROM runs WHERE seed=?", (seed,)
    ).fetchone()[0] == 0:
        run_seed(conn, seed=seed)

    primary_override = "__dead_primary_for_fallback_test__" if test_fallback else None
    if test_fallback:
        from sbe import config

        if not config.INVESTIGATOR_FALLBACK_API_KEY:
            raise typer.BadParameter(
                "INVESTIGATOR_FALLBACK_* must be set for --test-fallback"
            )
        rprint("[cyan]test-fallback[/cyan] primary model forced dead; expect fallback")

    verdicts, report = investigate_open_breaks(
        conn,
        seed=seed,
        limit=None if smoke else (limit if limit is not None else INVESTIGATE_PER_RUN_CAP),
        smoke=smoke,
        subsample=subsample,
        primary_model_override=primary_override,
    )
    from sbe.scoring.harness import format_pass1_report

    rprint(format_pass1_report(report))
    if report.quota_exhausted:
        rprint(
            f"[red]quota exhausted[/red] — {len(verdicts)} verdict(s) checkpointed; "
            f"reset ~{report.quota_reset_hint or 'unknown'}. "
            "Smoke with `--smoke` before full runs."
        )
    if test_fallback and verdicts:
        bid = verdicts[0].break_id
        prov = conn.execute(
            """
            SELECT new_value FROM audit_log
             WHERE break_id=? AND who='l3_investigator' AND what='provider'
             ORDER BY audit_id DESC LIMIT 1
            """,
            (bid,),
        ).fetchone()
        if not prov or '"fallback": true' not in (prov[0] or "").replace(" ", ""):
            conn.close()
            raise SystemExit(
                f"--test-fallback failed: no fallback=true in audit_log for {bid}"
            )
        rprint(f"[green]fallback OK[/green] audit_log provider={prov[0][:120]}")
    conn.close()

    if not verdicts:
        rprint(f"[yellow]no OPEN breaks[/yellow] seed={seed}")
        return

    by_verdict: dict[str, int] = {}
    for v in verdicts:
        by_verdict[v.verdict] = by_verdict.get(v.verdict, 0) + 1
    bad_match = [
        v
        for v in verdicts
        if v.verdict == "MATCH" and v.residual_unexplained != "0.00"
    ]
    if bad_match:
        raise SystemExit(
            f"contract violation: {len(bad_match)} MATCH verdict(s) with non-zero residual"
        )
    rprint(
        f"[green]investigate OK[/green] seed={seed} n={len(verdicts)} "
        f"verdicts={by_verdict}"
    )


@app.command()
def score(
    seed: str = "1001",
    print_table: bool = False,
    skip_investigate: bool = False,
    investigate_limit: int = typer.Option(
        None,
        "--investigate-limit",
        help="Cap L3 calls (stratified across archetypes). Default: INVESTIGATE_PER_RUN_CAP.",
    ),
):
    """Print headline metrics + per-archetype table (L3 verdicts only)."""
    from sbe.config import DB_PATH, INVESTIGATE_PER_RUN_CAP
    from sbe.db.connection import get_connection
    from sbe.engine.l3_investigator import investigate_open_breaks
    from sbe.generator.seed import SEEDS_ROOT
    from sbe.scoring.harness import (
        GATE5_ARITHMETIC_ARCHETYPES,
        GATE5_CORE_ARITHMETIC,
        adversarial_metrics,
        format_pass1_report,
        gate5_archetype_coverage,
        leakage_recall,
        match_residual_violations,
        net_accuracy_lift,
        per_archetype_table,
        value_weighted_reconciled_pct,
    )

    if not (SEEDS_ROOT / seed / "manifest.json").exists():
        raise typer.BadParameter(f"seed {seed} missing — run sbe generate first")

    db_path = Path(DB_PATH).parent / f"sbe_{seed}.db"
    if not db_path.exists():
        raise typer.BadParameter(f"no db for seed {seed} — run `sbe run --seed {seed}` first")

    conn = get_connection(str(db_path))
    open_no_verdict = conn.execute(
        """
        SELECT COUNT(*) FROM breaks
         WHERE seed = ? AND status = 'OPEN' AND verdict IS NULL
        """,
        (seed,),
    ).fetchone()[0]

    if open_no_verdict and not skip_investigate:
        cap = investigate_limit if investigate_limit is not None else INVESTIGATE_PER_RUN_CAP
        rprint(
            f"[cyan]investigating[/cyan] {open_no_verdict} OPEN break(s) "
            f"(stratified cap={cap})…"
        )
        _, report = investigate_open_breaks(conn, seed=seed, limit=cap)
        rprint(format_pass1_report(report))
        if not report.pass1_core_complete:
            rprint(
                "[yellow]Gate 5 not ready[/yellow]: pass-1 core trio incomplete "
                f"({', '.join(GATE5_CORE_ARITHMETIC)}) — see statuses above; "
                "do not trust arithmetic-heavy table rows yet"
            )

    table = per_archetype_table(conn, seed)
    vw = value_weighted_reconciled_pct(conn, seed)
    leak = leakage_recall(conn, seed)
    bad_match = match_residual_violations(conn, seed)
    adv = adversarial_metrics(conn, seed)
    g5 = gate5_archetype_coverage(conn, seed)
    net_lift, false_overturn = net_accuracy_lift(conn, seed)
    conn.close()

    if bad_match:
        raise SystemExit(
            f"contract violation: MATCH with non-zero residual: {bad_match[:5]}"
        )

    if table.empty:
        rprint("[yellow]no investigator verdicts yet[/yellow]")
        return

    if print_table:
        display = table.copy()
        if not display.empty:
            display["acc"] = display["acc"].map(lambda x: f"{x:.1f}%")
            display["verifier_lift"] = display["verifier_lift"].map(
                lambda x: f"{x:+.1f}pp"
            )
        rprint(display.to_string(index=False))

    missing_g5 = [a for a in GATE5_ARITHMETIC_ARCHETYPES if g5.get(a, 0) == 0]
    missing_core = [a for a in GATE5_CORE_ARITHMETIC if g5.get(a, 0) == 0]
    if missing_core:
        rprint(
            f"[yellow]GATE 5 core gap[/yellow]: no L3 verdict yet for "
            f"{', '.join(missing_core)}"
        )
    elif missing_g5:
        rprint(
            f"[yellow]GATE 5 partial[/yellow]: core trio covered; still missing "
            f"{', '.join(missing_g5)}"
        )

    leak_str = f"{leak:.1f}%" if leak == leak else "n/a"
    lift_str = f"{net_lift:+.1f}pp" if net_lift == net_lift else "n/a"
    overturn_str = (
        f"{false_overturn:.1f}%" if false_overturn == false_overturn else "n/a"
    )
    rprint(
        f"[green]score OK[/green] seed={seed} "
        f"l3_archetypes={len(table)} value_weighted_match={vw:.1f}% "
        f"leakage_recall={leak_str} net_verifier_lift={lift_str} "
        f"false_overturn_rate={overturn_str}"
    )

    if adv["n"]:
        rprint(
            f"  ADVERSARIAL_NARRATION (L3 n={adv['n']}): "
            f"resisted_injection={adv['resisted_injection']}/{adv['n']} "
            f"({adv['resisted_pct']:.1f}%) | "
            f"correct_verdict={adv['correct_verdict']}/{adv['n']} "
            f"({adv['correct_pct']:.1f}%)"
        )
        for row in adv.get("rows") or []:
            tools = json.loads(row.get("tools_called_json") or "[]")
            rprint(
                f"    {row['break_id']}: verdict={row.get('verdict')} "
                f"residual={row.get('residual_unexplained')} tools={tools}"
            )
            if row.get("verdict") == "MATCH" and not tools:
                raise SystemExit(
                    f"ADVERSARIAL auto-match: {row['break_id']} MATCH with no tools_called"
                )


@app.command()
def verify(
    seed: str = "1001",
    limit: int = typer.Option(
        None,
        "--limit",
        help="Cap L4 verifier calls (default: all L3-verdicted breaks without L4).",
    ),
):
    """Run L4 verifier on investigator verdicts (GATE 6)."""
    from sbe.config import DB_PATH
    from sbe.db.connection import get_connection
    from sbe.engine.l4_verifier import verify_l3_breaks
    from sbe.generator.seed import SEEDS_ROOT
    from sbe.scoring.harness import l3_investigated_break_ids, net_accuracy_lift

    if not (SEEDS_ROOT / seed / "manifest.json").exists():
        raise typer.BadParameter(f"seed {seed} missing — run sbe generate first")

    db_path = Path(DB_PATH).parent / f"sbe_{seed}.db"
    if not db_path.exists():
        raise typer.BadParameter(
            f"no db for seed {seed} — run `sbe run --seed {seed}` first"
        )

    conn = get_connection(str(db_path))
    l3_n = len(l3_investigated_break_ids(conn, seed))
    if l3_n == 0:
        rprint("[yellow]no L3 investigator verdicts — run sbe investigate or sbe score[/yellow]")
        conn.close()
        return

    pending = conn.execute(
        """
        SELECT COUNT(*) FROM breaks
         WHERE seed = ? AND break_id IN (
               SELECT break_id FROM audit_log
                WHERE who = 'l3_investigator' AND what = 'verdict'
             )
           AND verifier_decision IS NULL
        """,
        (seed,),
    ).fetchone()[0]
    rprint(
        f"[cyan]verifying[/cyan] up to {limit or pending} of {pending} pending "
        f"({l3_n} L3 total)…"
    )
    decisions = verify_l3_breaks(conn, seed=seed, limit=limit)
    net_lift, false_overturn = net_accuracy_lift(conn, seed)
    conn.close()

    uphold = sum(1 for d in decisions if d.decision == "UPHOLD")
    overturn = sum(1 for d in decisions if d.decision == "OVERTURN")
    escalate = sum(1 for d in decisions if d.decision == "ESCALATE")
    lift_str = f"{net_lift:+.1f}pp" if net_lift == net_lift else "n/a"
    overturn_str = (
        f"{false_overturn:.1f}%" if false_overturn == false_overturn else "n/a"
    )
    rprint(
        f"[green]verify OK[/green] seed={seed} ran={len(decisions)} "
        f"uphold={uphold} overturn={overturn} escalate={escalate} "
        f"net_lift={lift_str} false_overturn_rate={overturn_str}"
    )


@app.command()
def budget(seed: str = "1001"):
    """Estimate L3 token budget vs TPD before a full investigate run."""
    from sbe.config import DB_PATH
    from sbe.db.connection import get_connection
    from sbe.generator.seed import SEEDS_ROOT
    from sbe.scoring.budget import estimate_investigate_budget, format_budget_report

    if not (SEEDS_ROOT / seed / "manifest.json").exists():
        raise typer.BadParameter(f"seed {seed} missing — run sbe generate first")

    db_path = Path(DB_PATH).parent / f"sbe_{seed}.db"
    if not db_path.exists():
        raise typer.BadParameter(f"no db for seed {seed} — run sbe run first")

    conn = get_connection(str(db_path))
    report = estimate_investigate_budget(conn, seed)
    conn.close()
    rprint(format_budget_report(report))


@app.command()
def check(what: str, seed: str = "1001", day: int = None):
    """Daily checks: surfacing | rollforward | idempotency | residuals."""
    if what == "surfacing":
        _check_surfacing(seed=seed)
    elif what == "idempotency":
        _check_idempotency(seed=seed, day=day or 1)
    elif what == "rollforward":
        _check_rollforward(seed=seed, day=day)
    elif what == "residuals":
        _check_residuals(seed=seed)
    else:
        raise typer.BadParameter(
            f"unknown check {what!r}; expected surfacing|idempotency|rollforward|residuals"
        )


def _check_surfacing(seed: str) -> None:
    from sbe.config import DB_PATH
    from sbe.db.connection import get_connection
    from sbe.engine.l1_surfacing_gate import check_l1_surfacing, format_surfacing_report

    db_path = Path(DB_PATH).parent / f"sbe_{seed}.db"
    if not db_path.exists():
        raise typer.BadParameter(f"no db for seed {seed} — run sbe run first")
    conn = get_connection(str(db_path))
    result = check_l1_surfacing(conn, seed)
    conn.close()
    rprint(format_surfacing_report(result))
    if not result["ok"]:
        raise SystemExit("SURFACING GATE FAIL — see docs/LABEL_DIAGNOSIS.md")


def _check_idempotency(seed: str, day: int) -> None:
    """Re-run one ledger day twice and assert byte-identical breaks snapshots."""
    from sbe.config import DB_PATH
    from sbe.db.connection import get_connection
    from sbe.engine.l2_break_ledger import breaks_snapshot, ingest_day_breaks

    run_date = date(2026, 3, 10) + timedelta(days=day - 1)
    specs = [
        {
            "merchant_id": "MERCH_0001",
            "side": "LEDGER_ONLY",
            "amount_delta": Decimal("-1000.00"),
            "match_key": f"IDEMP-{seed}-{day}",
            "ground_truth_archetype": "T2_PERIOD_BOUNDARY",
        },
        {
            "merchant_id": "MERCH_0002",
            "side": "AMOUNT_MISMATCH",
            "amount_delta": Decimal("-42.00"),
            "match_key": f"IDEMP2-{seed}-{day}",
            "ground_truth_archetype": "FEE_PLUS_GST",
        },
    ]

    db_path = Path(DB_PATH).parent / f"idempotency_check_{seed}_day{day:02d}.db"
    if db_path.exists():
        db_path.unlink()
    conn = get_connection(str(db_path))
    ingest_day_breaks(conn, seed=seed, run_date=run_date, break_specs=specs)
    snap1 = breaks_snapshot(conn, seed)
    ingest_day_breaks(conn, seed=seed, run_date=run_date, break_specs=specs)
    snap2 = breaks_snapshot(conn, seed)
    conn.close()

    if snap1 != snap2:
        raise SystemExit(f"IDEMPOTENCY FAIL seed={seed} day={day}: snapshots differ")
    rprint(f"[green]idempotency OK[/green] seed={seed} day={day} db={db_path.name}")


def _check_rollforward(seed: str, day: int | None) -> None:
    """Run L1+L2+L5 and assert the roll-forward certificate ties."""
    from sbe.config import DB_PATH
    from sbe.db.connection import get_connection
    from sbe.engine.l5_rollforward import RollForwardBreak
    from sbe.engine.pipeline import run_day, run_seed
    from sbe.generator.seed import SEEDS_ROOT

    if not (SEEDS_ROOT / seed / "manifest.json").exists():
        raise typer.BadParameter(f"seed {seed} missing — run sbe generate first")

    db_path = Path(DB_PATH).parent / f"rollforward_check_{seed}.db"
    if db_path.exists():
        db_path.unlink()
    conn = get_connection(str(db_path))
    try:
        if day is not None:
            # Need prior days for opening balance continuity
            for d in range(1, day + 1):
                result = run_day(conn, seed=seed, day=d)
            cert = result["certificate"]
            rprint(
                f"[green]rollforward OK[/green] seed={seed} day={day} "
                f"closing={cert['closing_count']}/{cert['closing_value']}"
            )
        else:
            results = run_seed(conn, seed=seed)
            assert all(r["certificate"]["ties"] for r in results)
            last = results[-1]["certificate"]
            rprint(
                f"[green]rollforward OK[/green] seed={seed} days={len(results)} "
                f"final_closing={last['closing_count']}/{last['closing_value']}"
            )
    except RollForwardBreak as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        conn.close()


def _check_residuals(seed: str) -> None:
    """Assert no L3 MATCH verdict carries a non-zero residual_unexplained."""
    from sbe.config import DB_PATH
    from sbe.db.connection import get_connection
    from sbe.scoring.harness import match_residual_violations

    db_path = Path(DB_PATH).parent / f"sbe_{seed}.db"
    if not db_path.exists():
        raise typer.BadParameter(
            f"no db for seed {seed} — run `sbe run --seed {seed}` or investigate first"
        )
    conn = get_connection(str(db_path))
    bad = match_residual_violations(conn, seed)
    n_l3 = conn.execute(
        """
        SELECT COUNT(DISTINCT break_id) FROM audit_log
         WHERE who='l3_investigator' AND what='verdict'
           AND break_id IN (SELECT break_id FROM breaks WHERE seed=?)
        """,
        (seed,),
    ).fetchone()[0]
    conn.close()
    if bad:
        raise SystemExit(
            f"RESIDUALS FAIL seed={seed}: L3 MATCH with non-zero residual: {bad[:5]}"
        )
    rprint(f"[green]residuals OK[/green] seed={seed} l3_verdicts={n_l3}")


if __name__ == "__main__":
    app()
