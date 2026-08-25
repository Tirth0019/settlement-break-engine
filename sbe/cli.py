"""
CLI entrypoint — `sbe <command>` (installed via pyproject [project.scripts]).

TODO: wire each command to the corresponding module. Kept as one file for
now; split if it grows past ~150 lines.
"""
import typer

app = typer.Typer(help="Settlement Break Engine")


@app.command()
def generate(seed: str = "1001", days: int = 10):
    """Generate a synthetic seed (ROADMAP.md Day 1-2)."""
    raise NotImplementedError


@app.command()
def validate(seed: str = "1001"):
    """Run the generator self-assertion pass (GATE 1)."""
    raise NotImplementedError


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
