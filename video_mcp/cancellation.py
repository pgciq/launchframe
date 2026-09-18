from __future__ import annotations

from collections.abc import Callable


class CancellationRequested(RuntimeError):
    """Raised when a user cancels a running generation operation."""


def check_cancel(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check and cancel_check():
        raise CancellationRequested("Operation cancelled by the user")
