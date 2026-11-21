"""Unit tests for the virtual ledger & risk engine."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import Store, RiskStop, DEFAULT_BALANCE


class VirtualBetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Store(Path(self.tempdir.name) / "test.sqlite3")
        self.cid = 12_345_678
        self.db.ensure(self.cid)
        self.db.update(self.cid, active=1)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_win_net_and_balance(self) -> None:
        with patch("engine.secrets.choice", return_value="BIG"):
            r = self.db.virtual_round(self.cid)
        self.assertEqual(r["net"], 90)
        self.assertEqual(r["balance"], DEFAULT_BALANCE + 90)
        self.assertEqual(self.db.today(self.cid)["count"], 1)

    def test_loss_net_and_balance(self) -> None:
        with patch("engine.secrets.choice", return_value="SMALL"):
            r = self.db.virtual_round(self.cid)
        self.assertEqual(r["net"], -100)
        self.assertEqual(r["balance"], DEFAULT_BALANCE - 100)

    def test_max_bets_auto_stop(self) -> None:
        self.db.update(self.cid, max_daily_bets=1)
        self.db.virtual_round(self.cid)
        with self.assertRaises(RiskStop):
            self.db.virtual_round(self.cid)

    def test_prospective_loss_limit_blocks_bet(self) -> None:
        self.db.update(self.cid, stake=200, stop_loss=100)
        with self.assertRaises(RiskStop):
            self.db.virtual_round(self.cid)
        self.assertEqual(self.db.today(self.cid)["count"], 0)

    def test_insufficient_balance(self) -> None:
        self.db.update(self.cid, balance=50, stake=100)
        with self.assertRaises(RiskStop):
            self.db.virtual_round(self.cid)

    def test_reset(self) -> None:
        self.db.virtual_round(self.cid)
        self.db.reset_demo(self.cid)
        self.assertEqual(self.db.get(self.cid)["balance"], DEFAULT_BALANCE)
        self.assertEqual(self.db.today(self.cid)["count"], 0)
        self.assertEqual(self.db.get(self.cid)["active"], 0)

    def test_pause_all_at_restart(self) -> None:
        self.db.update(self.cid, active=1)
        self.db.pause_all_at_restart()
        self.assertEqual(self.db.get(self.cid)["active"], 0)


if __name__ == "__main__":
    unittest.main()
