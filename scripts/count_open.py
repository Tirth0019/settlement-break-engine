import sqlite3

for seed in ("1001", "2001"):
    c = sqlite3.connect(f"runs/sbe_{seed}.db")
    total = c.execute(
        "SELECT COUNT(*) FROM breaks WHERE seed=? AND status='OPEN'", (seed,)
    ).fetchone()[0]
    labeled = c.execute(
        "SELECT COUNT(*) FROM breaks WHERE seed=? AND status='OPEN' AND ground_truth_archetype IS NOT NULL",
        (seed,),
    ).fetchone()[0]
    null = total - labeled
    print(f"seed {seed}: OPEN total={total} labeled={labeled} null={null}")
    c.close()
