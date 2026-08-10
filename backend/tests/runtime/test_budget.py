from concurrent.futures import ThreadPoolExecutor

from backend.agent.runtime.budget import BudgetExceededError, BudgetLedger
from backend.agent.runtime.contracts import RunBudget


def _budget(max_tool_calls=4):
    return RunBudget(
        max_model_calls=2,
        max_tool_calls=max_tool_calls,
        max_input_tokens=100,
        max_output_tokens=100,
        max_cost_usd=None,
        max_loop_iterations=2,
    )


def test_parallel_reservations_never_exceed_limit():
    ledger = BudgetLedger(_budget(max_tool_calls=4))

    def reserve():
        try:
            ledger.reserve_tool()
            return True
        except BudgetExceededError:
            return False

    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(lambda _: reserve(), range(12)))

    assert outcomes.count(True) == 4
    assert ledger.snapshot().tool_calls == 4


def test_model_settlement_accounts_for_actual_usage():
    ledger = BudgetLedger(_budget())
    reservation = ledger.reserve_model(input_tokens=10, output_tokens=20)
    ledger.settle_model(reservation, actual_input_tokens=8, actual_output_tokens=12)

    assert ledger.snapshot().model_calls == 1
    assert ledger.snapshot().input_tokens == 8
    assert ledger.snapshot().output_tokens == 12
