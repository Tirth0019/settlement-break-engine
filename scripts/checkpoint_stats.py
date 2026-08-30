"""Quick post-run checkpoint stats."""
import sqlite3

conn = sqlite3.connect("runs/sbe_1001.db")
print("OPEN by side:", conn.execute(
    "SELECT side, COUNT(*) FROM breaks WHERE seed='1001' AND status='OPEN' GROUP BY side"
).fetchall())
print("OPEN null archetype:", conn.execute(
    "SELECT COUNT(*) FROM breaks WHERE seed='1001' AND status='OPEN' AND ground_truth_archetype IS NULL"
).fetchone()[0])
print("OPEN labeled:", conn.execute(
    "SELECT ground_truth_archetype, COUNT(*) FROM breaks WHERE seed='1001' AND status='OPEN' AND ground_truth_archetype IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"
).fetchall())
conn.close()
