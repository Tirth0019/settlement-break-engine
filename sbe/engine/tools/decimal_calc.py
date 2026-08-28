"""
decimal_calc — the only place arithmetic happens outside fee_recompute.

Design principle L6 (BUILD_PLAN): the model picks the hypothesis, a
deterministic tool does the maths. If you find yourself letting an LLM
add two numbers in its own output text, that is the top cause of quiet
accuracy rot (Risk R4) — route it through here instead, and log the call.
"""
from __future__ import annotations

import ast
import operator
from decimal import Decimal
from typing import Any

from sbe.money import money

# Call log for R4 diffs / cost metrics (append-only for the process).
CALL_LOG: list[dict[str, Any]] = []

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
}


def _log(op: str, inputs: dict, result: Decimal) -> Decimal:
    CALL_LOG.append({"op": op, "inputs": inputs, "result": f"{result:.2f}"})
    return result


def add(*values) -> Decimal:
    result = money(sum(money(v) for v in values)) if values else money(0)
    return _log("add", {"values": [f"{money(v):.2f}" for v in values]}, result)


def subtract(a, b) -> Decimal:
    result = money(money(a) - money(b))
    return _log("subtract", {"a": f"{money(a):.2f}", "b": f"{money(b):.2f}"}, result)


def residual(claimed_gap: Decimal, explained_amounts: list) -> Decimal:
    """The core residual_unexplained computation every investigator verdict
    depends on. Must be exact to the paise."""
    explained = add(*explained_amounts) if explained_amounts else money(0)
    result = money(money(claimed_gap) - explained)
    return _log(
        "residual",
        {
            "claimed_gap": f"{money(claimed_gap):.2f}",
            "explained_amounts": [f"{money(v):.2f}" for v in explained_amounts],
        },
        result,
    )


def _eval_node(node: ast.AST) -> Decimal:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
        return money(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return money(-_eval_node(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        op = _BINOPS[type(node.op)]
        if isinstance(node.op, ast.Div) and right == 0:
            raise ZeroDivisionError("division by zero in decimal_calc")
        return money(op(left, right))
    raise ValueError(f"disallowed expression node: {type(node).__name__}")


def calc(expr: str) -> Decimal:
    """Evaluate a tiny arithmetic expression with Decimal ROUND_HALF_UP money."""
    tree = ast.parse(str(expr).strip(), mode="eval")
    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.Call,
                ast.Attribute,
                ast.Name,
                ast.Subscript,
                ast.List,
                ast.Dict,
                ast.Tuple,
                ast.Lambda,
                ast.Compare,
                ast.BoolOp,
            ),
        ):
            raise ValueError(f"disallowed syntax in decimal_calc: {type(node).__name__}")
    result = money(_eval_node(tree))
    return _log("calc", {"expr": str(expr)}, result)


def clear_log() -> None:
    CALL_LOG.clear()
