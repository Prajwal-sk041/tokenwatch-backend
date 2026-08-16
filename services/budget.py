from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    blocked: bool
    action: str
    reason: str
    remaining_budget: Decimal | None
    current_usage: Decimal


def evaluate_budget(current: Decimal, estimated: Decimal, amount: Decimal | None, warning_percent: Decimal = Decimal("80"), hard_stop_percent: Decimal = Decimal("100"), action: str = "block") -> BudgetDecision:
    if amount is None:
        return BudgetDecision(True, False, "allow", "No matching budget", None, current)
    projected = current + estimated
    hard_limit = amount * hard_stop_percent / Decimal(100)
    warning_limit = amount * warning_percent / Decimal(100)
    remaining = amount - current
    if projected >= hard_limit and action == "block":
        return BudgetDecision(False, True, "block", "Hard budget threshold reached", remaining, current)
    if projected >= warning_limit:
        return BudgetDecision(True, False, "warn" if action != "log" else "log", "Budget warning threshold reached", remaining, current)
    return BudgetDecision(True, False, "allow", "Within budget", remaining, current)
