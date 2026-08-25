"""
CLI entrypoint — `sbe <command>` (installed via pyproject [project.scripts]).
"""
from __future__ import annotations

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
        raise typer.BadParameter(f"seed directory missing: {seed_dir} — run `sbe generate --seed {seed}` first")

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
    raise NotImplementedError


if __name__ == "__main__":
    app()
