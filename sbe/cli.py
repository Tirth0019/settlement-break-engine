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
    """Run the full L1-L7 pipeline for one day (or all days if date omitted)."""
    raise NotImplementedError


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
        raise NotImplementedError("rollforward check arrives Day 4")
    elif what == "residuals":
        raise NotImplementedError("residuals check arrives with L3")
    else:
        raise typer.BadParameter(f"unknown check {what!r}; expected idempotency|rollforward|residuals")


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

    # Isolated DB so the check is hermetic and re-runnable.
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


if __name__ == "__main__":
    app()
