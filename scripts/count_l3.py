import sqlite3

conn = sqlite3.connect("runs/sbe_2001.db")
v = conn.execute(
    "SELECT COUNT(1) FROM breaks WHERE seed='2001' AND verdict IS NOT NULL"
).fetchone()[0]
a = conn.execute(
    "SELECT COUNT(1) FROM audit_log WHERE who='l3_investigator' AND what='verdict'"
).fetchone()[0]
by_arch = conn.execute(
    """
    SELECT ground_truth_archetype, verdict, COUNT(1)
      FROM breaks
     WHERE seed='2001' AND verdict IS NOT NULL
     GROUP BY 1, 2
     ORDER BY 1, 2
    """
).fetchall()
print(f"breaks_with_verdict={v} audit_verdict_rows={a}")
for row in by_arch:
    print(row)
conn.close()
