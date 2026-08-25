"""
CLI entrypoint — `sbe <command>` (installed via pyproject [project.scripts]).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import typer
from rich import print as rprint

app = typer.Typer(help="Settlement Break Engine")


@app.command()
def generate(seed: str = "1001", days: int = 10):
    """Generate a synthetic seed (ROADMAP.md Day 1-2)."""
    from sbe.generator.seed import generate_seed

    out = generate_seed(seed=seed, days=days)
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
def score(seed: str = "1001", print_table: bool = False):
    """Print headline metrics + per-archetype table."""
    raise NotImplementedError


@app.command()
def check(what: str, seed: str = "1001", day: int = None):
    """Individual daily-check items: rollforward | idempotency | residuals."""
    if what == "idempotency":
        _check_idempotency(seed=seed, day=day or 1)
    elif what == "rollforward":
        _check_rollforward(seed=seed, day=day)
    elif what == "residuals":
        raise NotImplementedError("residuals check arrives with L3")
    else:
        raise typer.BadParameter(
            f"unknown check {what!r}; expected idempotency|rollforward|residuals"
        )


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


if __name__ == "__main__":
    app()
