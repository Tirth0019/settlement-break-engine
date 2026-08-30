"""Hold-out seed 9999 surfacing counts (docs/FINAL_PLAN.md §1.1)."""
import sqlite3
from pathlib import Path

SEED = "9999"
db = Path("runs") / f"sbe_{SEED}.db"
conn = sqlite3.connect(str(db))
print("OPEN labeled:")
for row in conn.execute(
    """
    SELECT ground_truth_archetype, COUNT(1)
      FROM breaks
     WHERE seed=? AND status='OPEN' AND ground_truth_archetype IS NOT NULL
     GROUP BY 1
     ORDER BY 2 DESC
    """,
    (SEED,),
):
    print(f"  {row[0]:28s} {row[1]}")
total = conn.execute(
    "SELECT COUNT(1) FROM breaks WHERE seed=? AND status='OPEN'", (SEED,)
).fetchone()[0]
nulls = conn.execute(
    """
    SELECT COUNT(1) FROM breaks
     WHERE seed=? AND status='OPEN' AND ground_truth_archetype IS NULL
    """,
    (SEED,),
).fetchone()[0]
labeled = total - nulls
print(f"OPEN total={total} labeled={labeled} unlabeled={nulls}")
if total:
    print(f"unlabeled_pct={100.0 * nulls / total:.1f}%")
conn.close()
