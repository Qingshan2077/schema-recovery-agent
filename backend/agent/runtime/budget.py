"""Per-run atomic budget reservation and settlement."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock

from backend.agent.runtime.contracts import RunBudget, RuntimeUsage


class BudgetExceededError(RuntimeError):
    def __init__(self, dimension: str, current: object, limit: object):
        super().__init__(f"Runtime budget exhausted for {dimension}")
        self.dimension = dimension
        self.current = current
        self.limit = limit


@dataclass(frozen=True)
class BudgetReservation:
    kind: str
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal = Decimal("0")


class BudgetLedger:
    """A lock-protected ledger safe for concurrent tasks in one process."""

    def __init__(self, budget: RunBudget):
        self.budget = budget
        self._usage = RuntimeUsage()
        self._lock = RLock()

    def reserve_model(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: Decimal = Decimal("0"),
    ) -> BudgetReservation:
        reservation = BudgetReservation(
            kind="model",
            calls=1,
            input_tokens=max(0, input_tokens),
            output_tokens=max(0, output_tokens),
            cost_usd=max(Decimal("0"), Decimal(cost_usd)),
        )
        with self._lock:
            self._check_deadline()
            self._assert_limit("model_calls", self._usage.model_calls + 1, self.budget.max_model_calls)
            self._assert_limit(
                "input_tokens", self._usage.input_tokens + reservation.input_tokens, self.budget.max_input_tokens
            )
            self._assert_limit(
                "output_tokens", self._usage.output_tokens + reservation.output_tokens, self.budget.max_output_tokens
            )
            if self.budget.max_cost_usd is not None:
                self._assert_limit(
                    "cost_usd", self._usage.cost_usd + reservation.cost_usd, self.budget.max_cost_usd
                )
            self._usage.model_calls += 1
            self._usage.input_tokens += reservation.input_tokens
            self._usage.output_tokens += reservation.output_tokens
            self._usage.cost_usd += reservation.cost_usd
        return reservation

    def settle_model(
        self,
        reservation: BudgetReservation,
        *,
        actual_input_tokens: int,
        actual_output_tokens: int,
        actual_cost_usd: Decimal = Decimal("0"),
    ) -> None:
        with self._lock:
            next_input = self._usage.input_tokens - reservation.input_tokens + max(0, actual_input_tokens)
            next_output = self._usage.output_tokens - reservation.output_tokens + max(0, actual_output_tokens)
            next_cost = self._usage.cost_usd - reservation.cost_usd + max(Decimal("0"), Decimal(actual_cost_usd))
            self._assert_limit("input_tokens", next_input, self.budget.max_input_tokens)
            self._assert_limit("output_tokens", next_output, self.budget.max_output_tokens)
            if self.budget.max_cost_usd is not None:
                self._assert_limit("cost_usd", next_cost, self.budget.max_cost_usd)
            self._usage.input_tokens = next_input
            self._usage.output_tokens = next_output
            self._usage.cost_usd = next_cost

    def reserve_tool(self) -> BudgetReservation:
        reservation = BudgetReservation(kind="tool", calls=1)
        with self._lock:
            self._check_deadline()
            self._assert_limit("tool_calls", self._usage.tool_calls + 1, self.budget.max_tool_calls)
            self._usage.tool_calls += 1
        return reservation

    def reserve_loop_iteration(self) -> BudgetReservation:
        reservation = BudgetReservation(kind="loop", calls=1)
        with self._lock:
            self._check_deadline()
            self._assert_limit(
                "loop_iterations", self._usage.loop_iterations + 1, self.budget.max_loop_iterations
            )
            self._usage.loop_iterations += 1
        return reservation

    def release(self, reservation: BudgetReservation) -> None:
        with self._lock:
            if reservation.kind == "model":
                self._usage.model_calls = max(0, self._usage.model_calls - reservation.calls)
                self._usage.input_tokens = max(0, self._usage.input_tokens - reservation.input_tokens)
                self._usage.output_tokens = max(0, self._usage.output_tokens - reservation.output_tokens)
                self._usage.cost_usd = max(Decimal("0"), self._usage.cost_usd - reservation.cost_usd)
            elif reservation.kind == "tool":
                self._usage.tool_calls = max(0, self._usage.tool_calls - reservation.calls)
            elif reservation.kind == "loop":
                self._usage.loop_iterations = max(0, self._usage.loop_iterations - reservation.calls)

    def snapshot(self) -> RuntimeUsage:
        with self._lock:
            return self._usage.model_copy(deep=True)

    def limits(self) -> dict[str, object]:
        return self.budget.model_dump(mode="json")

    def _check_deadline(self) -> None:
        deadline = self.budget.deadline_at
        if deadline is None:
            return
        now = datetime.now(timezone.utc)
        comparable = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
        if now >= comparable:
            raise BudgetExceededError("deadline_at", now.isoformat(), comparable.isoformat())

    @staticmethod
    def _assert_limit(dimension: str, current: object, limit: object) -> None:
        if current > limit:
            raise BudgetExceededError(dimension, current, limit)
