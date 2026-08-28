"""Day 6 EOD spot-check — verdicts, residuals, adversarial rows."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from sbe.config import DB_PATH
from sbe.money import money
from sbe.scoring.harness import (
    adversarial_narration_rows,
    join_breaks_to_ground_truth,
    per_archetype_table,
)

db = Path(DB_PATH).parent / "sbe_1001.db"
conn = sqlite3.connect(db)

n = conn.execute(
    "SELECT COUNT(*) FROM breaks WHERE seed=? AND verdict IS NOT NULL", ("1001",)
).fetchone()[0]
print(f"verdicts={n}")

bad = conn.execute(
    """
    SELECT break_id, residual_unexplained FROM breaks
     WHERE seed='1001' AND verdict='MATCH'
       AND residual_unexplained IS NOT NULL
    """
).fetchall()
bad = [b for b in bad if money(b[1]) != money(0)]
print(f"MATCH non-zero residual count={len(bad)}")
if bad:
    print("violations:", bad[:5])

table = per_archetype_table(conn, "1001")
print("\nper-archetype table:")
if table.empty:
    print("(empty — no verdicts yet)")
else:
    print(table.to_string(index=False))

print("\nADVERSARIAL_NARRATION rows:")
for row in adversarial_narration_rows(conn, "1001"):
    if row.get("verdict"):
        tools = json.loads(row.get("tools_called_json") or "[]")
        print(
            f"  {row['break_id']}: verdict={row['verdict']} "
            f"residual={row.get('residual_unexplained')} tools={tools}"
        )

conn.close()
