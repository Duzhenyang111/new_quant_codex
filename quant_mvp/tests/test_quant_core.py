import json
import tempfile
import unittest
from pathlib import Path

from quant_core.account.ledger import Account, Position
from quant_core.data.akshare_adapter import normalize_daily_rows
from quant_core.data.downloader import download_symbols, list_a_share_symbols
from quant_core.data.index_adapter import normalize_index_rows
from quant_core.data.sqlite_store import (
    count_bars,
    import_bars_csv,
    init_database,
    latest_bar_date_by_symbol,
    upsert_indices,
    upsert_bars,
)
from quant_core.execution.simulator import execute_plan_at_open
from quant_core.reports.daily_review import build_daily_review
from quant_core.run_daily import _reason_from_metrics, run_daily
from quant_core.strategy.stock_selector import select_stocks


def bar(date, symbol, open_, close, amount=50_000_000, paused=False, st=False):
    return {
        "date": date,
        "symbol": symbol,
        "open": open_,
        "high": max(open_, close) * 1.01,
        "low": min(open_, close) * 0.99,
        "close": close,
        "volume": 1_000_000,
        "amount": amount,
        "paused": paused,
        "is_st": st,
        "limit_up": False,
        "limit_down": False,
    }


def rising_history(symbol, start_price, step, days=70):
    rows = []
    price = start_price
    for i in range(days):
        date = f"2026-03-{i + 1:02d}" if i < 31 else f"2026-04-{i - 30:02d}"
        open_ = price
        price = round(price + step, 2)
        rows.append(bar(date, symbol, open_, price))
    return rows


class QuantCoreTests(unittest.TestCase):
    def test_akshare_rows_are_normalized_to_internal_bar_schema(self):
        rows = normalize_daily_rows(
            "600001.SH",
            [
                {
                    "\u65e5\u671f": "2026-05-15",
                    "\u5f00\u76d8": 10,
                    "\u6536\u76d8": 10.5,
                    "\u6700\u9ad8": 10.8,
                    "\u6700\u4f4e": 9.9,
                    "\u6210\u4ea4\u91cf": 1000,
                    "\u6210\u4ea4\u989d": 50_000_000,
                }
            ],
        )

        self.assertEqual(rows[0]["symbol"], "600001.SH")
        self.assertEqual(rows[0]["open"], 10.0)
        self.assertFalse(rows[0]["paused"])

    def test_download_symbols_writes_bars_and_status_without_paid_data_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)

            def fake_fetch(symbol, start_date, end_date):
                return [bar(start_date, symbol, 10, 11)]

            status = download_symbols(
                workspace,
                symbols=["600001.SH", "000001.SZ"],
                start_date="2026-05-01",
                end_date="2026-05-15",
                fetcher=fake_fetch,
            )

            self.assertEqual(status["ok_symbols"], ["600001.SH", "000001.SZ"])
            self.assertEqual(status["failed_symbols"], {})
            self.assertEqual(status["rows"], 2)
            self.assertTrue((workspace / "data" / "bars.csv").exists())
            self.assertTrue((workspace / "data" / "status.json").exists())

    def test_index_rows_are_normalized_to_internal_bar_schema(self):
        rows = normalize_index_rows(
            "000001.SH",
            "上证指数",
            [
                {
                    "date": "2026-05-13",
                    "open": 4192.315,
                    "high": 4245.068,
                    "low": 4192.315,
                    "close": 4242.572,
                    "volume": 70501873900,
                }
            ],
        )

        self.assertEqual(rows[0]["symbol"], "000001.SH")
        self.assertEqual(rows[0]["name"], "上证指数")
        self.assertAlmostEqual(rows[0]["daily_return"], 4242.572 / 4192.315 - 1)

    def test_download_symbols_can_cache_per_symbol_for_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)

            def fake_fetch(symbol, start_date, end_date):
                return [bar(start_date, symbol, 10, 11)]

            status = download_symbols(
                workspace,
                symbols=["600001.SH", "000001.SZ"],
                start_date="2026-05-01",
                end_date="2026-05-15",
                fetcher=fake_fetch,
                cache_per_symbol=True,
            )

            self.assertEqual(status["rows"], 2)
            self.assertTrue((workspace / "data" / "symbols" / "600001.SH.csv").exists())
            self.assertTrue((workspace / "data" / "symbols" / "000001.SZ.csv").exists())
            self.assertTrue((workspace / "data" / "bars.csv").exists())

    def test_sqlite_store_upserts_and_reports_latest_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "market_data.sqlite"
            init_database(db_path)

            upsert_bars(
                db_path,
                [
                    bar("2026-05-14", "600001.SH", 10, 11),
                    bar("2026-05-15", "600001.SH", 11, 12),
                    bar("2026-05-15", "000001.SZ", 9, 9.5),
                ],
            )
            upsert_bars(db_path, [bar("2026-05-15", "600001.SH", 11, 12.5)])

            self.assertEqual(count_bars(db_path), 3)
            self.assertEqual(
                latest_bar_date_by_symbol(db_path),
                {"000001.SZ": "2026-05-15", "600001.SH": "2026-05-15"},
            )

    def test_sqlite_store_imports_existing_bars_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            rows = [bar("2026-05-14", "600001.SH", 10, 11), bar("2026-05-15", "000001.SZ", 9, 9.5)]
            csv_path = workspace / "bars.csv"
            with csv_path.open("w", encoding="utf-8") as handle:
                handle.write(",".join(rows[0].keys()) + "\n")
                for row in rows:
                    handle.write(",".join(str(value) for value in row.values()) + "\n")

            db_path = workspace / "market_data.sqlite"
            imported = import_bars_csv(csv_path, db_path)

            self.assertEqual(imported, 2)
            self.assertEqual(count_bars(db_path), 2)

    def test_list_a_share_symbols_normalizes_exchange_suffixes(self):
        rows = [
            {"code": "600001", "name": "Shanghai"},
            {"code": "000001", "name": "Shenzhen"},
            {"code": "430001", "name": "Beijing"},
        ]

        self.assertEqual(
            list_a_share_symbols(rows=rows),
            ["600001.SH", "000001.SZ", "430001.BJ"],
        )

    def test_selector_filters_invalid_a_share_rows_and_ranks_momentum(self):
        history = {
            "600001.SH": rising_history("600001.SH", 10, 0.20),
            "000001.SZ": rising_history("000001.SZ", 10, 0.05),
            "300001.SZ": rising_history("300001.SZ", 10, 0.30, days=12),
            "600999.SH": [bar("2026-04-01", "600999.SH", 10, 10, st=True)] * 70,
        }

        result = select_stocks(
            history,
            trade_date="2026-04-39",
            top_n=2,
            min_history_days=60,
            min_amount=10_000_000,
        )

        self.assertEqual([pick.symbol for pick in result.picks], ["600001.SH", "000001.SZ"])
        self.assertGreater(result.picks[0].score, result.picks[1].score)
        self.assertIn("300001.SZ", result.rejected)
        self.assertIn("600999.SH", result.rejected)

    def test_execution_uses_today_open_and_respects_lot_size_and_costs(self):
        account = Account(
            cash=100_000,
            positions={"000001.SZ": Position(symbol="000001.SZ", quantity=1000, cost_basis=8.0)},
        )
        plan = {
            "trade_date": "2026-05-14",
            "execute_date": "2026-05-15",
            "orders": [
                {"symbol": "000001.SZ", "action": "sell", "target_weight": 0.0, "reason": "exit"},
                {"symbol": "600001.SH", "action": "buy", "target_weight": 0.5, "reason": "rank_1"},
            ],
        }
        today_bars = {
            "000001.SZ": bar("2026-05-15", "000001.SZ", 10.0, 10.2),
            "600001.SH": bar("2026-05-15", "600001.SH", 20.0, 20.8),
        }

        result = execute_plan_at_open(account, plan, today_bars)

        self.assertEqual(result.trades[0].price, 10.0)
        self.assertEqual(result.trades[1].price, 20.0)
        self.assertEqual(result.account.positions["000001.SZ"].quantity, 0)
        self.assertEqual(result.account.positions["600001.SH"].quantity % 100, 0)
        self.assertLess(result.account.cash, 110_000)

    def test_daily_review_contains_report_style_metrics_and_holdings(self):
        account = Account(
            cash=50_000,
            positions={"600001.SH": Position(symbol="600001.SH", quantity=1000, cost_basis=10.0)},
        )
        execution = execute_plan_at_open(account, {"orders": []}, {"600001.SH": bar("2026-05-15", "600001.SH", 10.0, 11.0)})
        selection = select_stocks({"600001.SH": rising_history("600001.SH", 10, 0.2)}, "2026-04-39", top_n=1)

        review = build_daily_review(
            "2026-05-15",
            execution.account,
            execution,
            selection,
            {"600001.SH": bar("2026-05-15", "600001.SH", 10.0, 11.0)},
        )

        self.assertEqual(review["portfolio"]["position_count"], 1)
        self.assertAlmostEqual(review["portfolio"]["stock_market_value"], 11000.0)
        self.assertEqual(review["holdings"][0]["symbol"], "600001.SH")
        self.assertAlmostEqual(review["holdings"][0]["position_pnl_pct"], 0.1)
        self.assertEqual(review["market"]["advance_count"], 1)
        self.assertIn("insights", review)

    def test_daily_review_uses_real_market_index_when_available(self):
        account = Account(cash=100_000, positions={})
        execution = execute_plan_at_open(account, {"orders": []}, {})
        selection = select_stocks({"600001.SH": rising_history("600001.SH", 10, 0.2)}, "2026-04-39", top_n=1)

        review = build_daily_review(
            "2026-05-15",
            execution.account,
            execution,
            selection,
            {},
            market_index={
                "symbol": "000001.SH",
                "name": "上证指数",
                "open": 4200.0,
                "close": 4242.0,
                "daily_return": 0.01,
            },
        )

        self.assertEqual(review["market"]["symbol"], "000001.SH")
        self.assertEqual(review["market"]["name"], "上证指数")
        self.assertEqual(review["market"]["daily_return"], 0.01)

    def test_plan_reason_uses_specific_factor_explanation(self):
        reason = _reason_from_metrics(
            {
                "momentum_20": 0.12,
                "momentum_60": 0.21,
                "trend": 0.08,
                "liquidity": 17.5,
                "low_volatility": -0.18,
            }
        )

        self.assertIn("20日动量 12.00%", reason)
        self.assertIn("60日动量 21.00%", reason)
        self.assertIn("均线趋势 8.00%", reason)
        self.assertNotIn("rank_", reason)

    def test_daily_run_executes_yesterday_plan_and_writes_review_and_next_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            data_dir = workspace / "data"
            plans_dir = workspace / "plans"
            account_dir = workspace / "account"
            reports_dir = workspace / "reports"
            for d in (data_dir, plans_dir, account_dir, reports_dir):
                d.mkdir(parents=True)

            rows = rising_history("600001.SH", 10, 0.20) + rising_history("000001.SZ", 10, 0.05)
            rows.extend(
                [
                    bar("2026-05-15", "600001.SH", 20.0, 20.5),
                    bar("2026-05-15", "000001.SZ", 10.0, 10.1),
                ]
            )
            with (data_dir / "bars.csv").open("w", encoding="utf-8") as f:
                f.write(",".join(rows[0].keys()) + "\n")
                for row in rows:
                    f.write(",".join(str(v) for v in row.values()) + "\n")

            (plans_dir / "2026-05-14.json").write_text(
                json.dumps(
                    {
                        "trade_date": "2026-05-14",
                        "execute_date": "2026-05-15",
                        "orders": [
                            {
                                "symbol": "600001.SH",
                                "action": "buy",
                                "target_weight": 0.5,
                                "reason": "rank_1",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (account_dir / "latest.json").write_text(
                json.dumps({"cash": 100_000, "positions": {}}),
                encoding="utf-8",
            )

            summary = run_daily(workspace, trade_date="2026-05-15", previous_trade_date="2026-05-14")

            self.assertTrue((account_dir / "2026-05-15.json").exists())
            self.assertTrue((plans_dir / "2026-05-15.json").exists())
            self.assertTrue((reports_dir / "2026-05-15.json").exists())
            self.assertGreaterEqual(len(summary["next_plan"]["orders"]), 1)

    def test_daily_run_can_read_market_data_from_sqlite_without_bars_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            data_dir = workspace / "data"
            plans_dir = workspace / "plans"
            account_dir = workspace / "account"
            for d in (data_dir, plans_dir, account_dir):
                d.mkdir(parents=True)

            db_path = data_dir / "market_data.sqlite"
            init_database(db_path)
            rows = rising_history("600001.SH", 10, 0.20) + rising_history("000001.SZ", 10, 0.05)
            rows.extend(
                [
                    bar("2026-05-15", "600001.SH", 20.0, 20.5),
                    bar("2026-05-15", "000001.SZ", 10.0, 10.1),
                ]
            )
            upsert_bars(db_path, rows)
            upsert_indices(
                db_path,
                [
                    {
                        "date": "2026-05-15",
                        "symbol": "000001.SH",
                        "name": "上证指数",
                        "open": 4200,
                        "high": 4250,
                        "low": 4180,
                        "close": 4242,
                        "volume": 1000,
                        "daily_return": 0.01,
                    }
                ],
            )
            (plans_dir / "2026-05-14.json").write_text(
                json.dumps(
                    {
                        "trade_date": "2026-05-14",
                        "execute_date": "2026-05-15",
                        "orders": [{"symbol": "600001.SH", "action": "buy", "target_weight": 0.5}],
                    }
                ),
                encoding="utf-8",
            )
            (account_dir / "latest.json").write_text(
                json.dumps({"cash": 100_000, "positions": {}}),
                encoding="utf-8",
            )

            summary = run_daily(workspace, trade_date="2026-05-15", previous_trade_date="2026-05-14")

            self.assertEqual(summary["review"]["market"]["symbol"], "000001.SH")
            self.assertTrue((workspace / "reports" / "latest.json").exists())
            self.assertGreaterEqual(len(summary["next_plan"]["orders"]), 1)


if __name__ == "__main__":
    unittest.main()
