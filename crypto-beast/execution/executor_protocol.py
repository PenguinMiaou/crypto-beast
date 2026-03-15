"""Protocol base class for executor implementations (paper + live)."""
from typing import List

from core.models import ExecutionPlan, ExecutionResult, OrderType, Position


class ExecutorProtocol:
    """Base class for executor implementations (paper + live).

    Defines the interface that PaperExecutor and LiveExecutor follow.
    Not using typing.Protocol due to Python 3.9 runtime_checkable limitations.
    """

    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        """Execute a trade plan."""
        raise NotImplementedError

    async def get_positions(self) -> List[Position]:
        """Fetch current open positions."""
        raise NotImplementedError

    async def close_position(
        self, position: Position, order_type: OrderType = OrderType.MARKET
    ) -> ExecutionResult:
        """Close an open position."""
        raise NotImplementedError

    async def cancel_all_pending(self) -> None:
        """Cancel all pending/open orders."""
        raise NotImplementedError
