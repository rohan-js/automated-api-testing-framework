import unittest

from api_test_framework.invariant_checker import InvariantChecker


class InvariantCheckerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.checker = InvariantChecker()

    def test_balance_non_negative_fails_for_negative_account(self) -> None:
        result = self.checker.check_balance_non_negative({"A": 10.0, "B": -1.0})
        self.assertFalse(result.passed)
        self.assertIn("B=-1.00", result.message)

    def test_money_conserved_passes_when_totals_match(self) -> None:
        before = {"A": 100.0, "B": 50.0}
        after = {"A": 90.0, "B": 60.0}
        result = self.checker.check_money_conserved(before, after)
        self.assertTrue(result.passed)

    def test_money_conserved_fails_when_totals_change(self) -> None:
        before = {"A": 100.0, "B": 50.0}
        after = {"A": 80.0, "B": 60.0}
        result = self.checker.check_money_conserved(before, after)
        self.assertFalse(result.passed)
        self.assertIn("delta", result.message)

    def test_idempotent_passes_for_identical_state(self) -> None:
        result = self.checker.check_idempotent({"A": 100.0}, {"A": 100.0})
        self.assertTrue(result.passed)

    def test_idempotent_fails_for_drift(self) -> None:
        result = self.checker.check_idempotent({"A": 100.0, "B": 20.0}, {"A": 95.0, "B": 25.0})
        self.assertFalse(result.passed)
        self.assertIn("A", result.message)


if __name__ == "__main__":
    unittest.main()
