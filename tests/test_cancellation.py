from __future__ import annotations

import unittest

from video_mcp.cancellation import CancellationRequested, check_cancel


class CheckCancelTests(unittest.TestCase):
    def test_none_check_does_nothing(self) -> None:
        check_cancel(None)  # must not raise

    def test_false_check_does_nothing(self) -> None:
        check_cancel(lambda: False)  # must not raise

    def test_true_check_raises_cancellation_requested(self) -> None:
        with self.assertRaises(CancellationRequested):
            check_cancel(lambda: True)

    def test_cancellation_requested_is_a_runtime_error(self) -> None:
        self.assertTrue(issubclass(CancellationRequested, RuntimeError))


if __name__ == "__main__":
    unittest.main()
