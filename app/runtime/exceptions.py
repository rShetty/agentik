"""Runtime-layer exception types."""


class InvalidTransitionError(ValueError):
    """Raised when an illegal lifecycle state transition is attempted."""


class BudgetExceededError(RuntimeError):
    """Raised when an agent's run budget has been exhausted."""
