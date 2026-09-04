"""Pick hold-out packet IDs and render packets + certificate."""
import sqlite3
from pathlib import Path

from sbe.db.connection import get_connection
from sbe.engine.certificate import publish_or_refuse, render_certificate
from sbe.engine.l5_rollforward import RollForwardBreak
from sbe.engine.l6_packets import render_break_packet
from sbe.scoring.cost import estimate_seed_cost, format_cost_report
from sbe.scoring.harness import l3_verdict_map

SEED = "9999"
conn = get_connection(f"runs/sbe_{SEED}.db")
l3 = l3_verdict_map(conn, SEED)
print(format_cost_report(estimate_seed_cost(conn, SEED)))

fee = None
leak = None
for row in conn.execute(
    """
    SELECT break_id, ground_truth_archetype, residual_unexplained, evidence_json,
           hypothesis, confidence, verifier_decision, amount_delta, age_days,
           merchant_id, verdict
      FROM breaks WHERE seed=?
    """,
    (SEED,),
):
    bid = row[0]
    arch = row[1]
    if bid not in l3:
        continue
    if arch == "FEE_PLUS_GST" and l3[bid] == "MATCH" and fee is None:
        fee = row
    if arch == "TRUE_LEAKAGE" and l3[bid] == "NEEDS_HUMAN" and leak is None:
        leak = row

out = Path("runs") / SEED / "packets"
out.mkdir(parents=True, exist_ok=True)

for label, row in (("fee_match", fee), ("leakage_needs_human", leak)):
    if not row:
        print(f"missing {label}")
        continue
    cols = [
        "break_id",
        "ground_truth_archetype",
        "residual_unexplained",
        "evidence_json",
        "hypothesis",
        "confidence",
        "verifier_decision",
        "amount_delta",
        "age_days",
        "merchant_id",
        "verdict",
    ]
    rec = dict(zip(cols, row))
    rec["verdict"] = l3[rec["break_id"]]  # L3 ground truth
    rec["archetype"] = rec["ground_truth_archetype"]
    text = render_break_packet(rec)
    path = out / f"{label}_{rec['break_id']}.txt"
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")

cert = render_certificate(conn, SEED, "2026-03-19")
print("certificate lines", len(cert.splitlines()))
try:
    publish_or_refuse(conn, SEED, "2026-03-19", inject_phantom=True)
except RollForwardBreak as e:
    print("phantom refuse OK:", str(e)[:80])
conn.close()
