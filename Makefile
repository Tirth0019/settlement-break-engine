.PHONY: setup generate validate run score test daily-check freeze

setup:
	python -m venv .venv
	. .venv/bin/activate && pip install -e ".[dev]"
	cp -n .env.example .env || true
	@echo "Now fill in .env — INVESTIGATOR_* and VERIFIER_* (BUILD_PLAN L2/L3)"

generate:
	sbe generate --seed 1001 --days 10

validate:
	sbe validate --seed 1001   # generator self-assertion pass (BUILD_PLAN Phase 1 / R1)

run:
	sbe run --seed 1001

score:
	sbe score --seed 1001

test:
	pytest -v

# BUILD_PLAN Part VII — run this every day of the build, in order.
daily-check:
	@echo "1/6 roll-forward ties?"      && sbe check rollforward --seed 1001
	@echo "2/6 idempotent re-run?"      && sbe check idempotency --seed 1001 --day 5
	@echo "3/6 fee_recompute matches generator?" && pytest tests/test_fee_recompute_matches_generator.py -q
	@echo "4/6 zero MATCH with nonzero residual?" && sbe check residuals --seed 1001
	@echo "5/6 per-archetype table regenerated"   && sbe score --seed 1001 --print-table
	@echo "6/6 current phase gate — check manually against BUILD_PLAN.md"

# BUILD_PLAN Phase 8 — run once, after which no prompt changes.
freeze:
	git tag agent-freeze
	@echo "Tagged agent-freeze. Do not edit sbe/engine/l3_investigator.py or l4_verifier.py after this point."
	sbe generate --seed 9999 --days 10
	sbe validate --seed 9999
	sbe run --seed 9999
	sbe score --seed 9999 --print-table
