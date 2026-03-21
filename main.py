#!/usr/bin/env python3
"""S&P Markets - Multi-Agent Trading Firm

Usage:
    python main.py run       # Execute the full analysis pipeline
    python main.py review    # Review expired trades and update memory bank
"""

import sys
import uuid
import logging
import argparse
from datetime import datetime

from graph.workflow import build_workflow
from agents.journal_agent import JournalAgent


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)-25s | %(levelname)-5s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # Reduce noise from third-party libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)


def run_pipeline():
    """Execute the full analysis pipeline: news → correlation → analysis → decision → risk → journal."""
    print("\n" + "=" * 70)
    print("  S&P MARKETS - MULTI-AGENT TRADING PIPELINE")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")

    workflow = build_workflow()
    run_id = str(uuid.uuid4())[:8]

    initial_state = {
        "news": None,
        "correlation": None,
        "affected_symbols": [],
        "ohlcv_data": {},
        "fundamentals": {},
        "market_context": None,
        "analyses": [],
        "dm_output": None,
        "rm_output": None,
        "run_id": run_id,
        "errors": [],
    }

    print(f"Starting pipeline run: {run_id}\n")
    result = workflow.invoke(initial_state)

    # Print results
    print("\n" + "=" * 70)
    print("  PIPELINE RESULTS")
    print("=" * 70)

    # News summary
    if result.get("news"):
        print(f"\nNews: {result['news'].count} articles scraped")

    # Correlation summary
    if result.get("correlation"):
        corr = result["correlation"]
        symbols = [s.symbol for s in corr.affected_stocks]
        print(f"Affected stocks: {len(symbols)} identified")
        print(f"  Symbols: {', '.join(symbols)}")
        print(f"  Market themes: {', '.join(corr.market_themes)}")
        print(f"  Overall sentiment: {corr.overall_sentiment}")

    # DM decisions
    if result.get("dm_output"):
        dm = result["dm_output"]
        print(f"\nDecision Maker ({dm.day_of_week}, {dm.current_date}):")
        print(f"  Market outlook: {dm.market_outlook}")
        for d in dm.decisions:
            if d.direction.value != "IGNORE":
                print(
                    f"  {d.direction.value:5s} {d.symbol:15s} "
                    f"entry={d.entry_price:>8.2f}  target={d.target_price:>8.2f}  "
                    f"conf={d.confidence:.2f}  days={d.timeframe_days}"
                )
            else:
                print(f"  IGNORE {d.symbol:15s} (balanced)")

    # RM output
    if result.get("rm_output"):
        rm = result["rm_output"]
        print(f"\nRisk Manager:")
        print(f"  VIX: {rm.vix_assessment}")
        print(f"  Portfolio risk: {rm.total_capital_at_risk_pct:.2f}%")
        print(f"  Approved: {len(rm.approved_trades)} | Rejected: {len(rm.rejected_trades)}")

        if rm.approved_trades:
            print("\n  APPROVED TRADES:")
            print(f"  {'Symbol':<12} {'Dir':>5} {'Entry':>8} {'Target':>8} {'SL':>8} {'Qty':>6} {'R:R':>5} {'MaxLoss':>10}")
            print("  " + "-" * 70)
            for t in rm.approved_trades:
                print(
                    f"  {t.symbol:<12} {t.direction:>5} {t.entry_price:>8.2f} "
                    f"{t.target_price:>8.2f} {t.stop_loss:>8.2f} {t.quantity:>6} "
                    f"{t.risk_reward_ratio:>5.2f} {t.max_loss_amount:>10.2f}"
                )

        if rm.rejected_trades:
            print("\n  REJECTED:")
            for r in rm.rejected_trades:
                print(f"  {r.get('symbol', '?'):12s} - {r.get('reason', '?')}")

    # Errors
    if result.get("errors"):
        print(f"\nErrors ({len(result['errors'])}):")
        for err in result["errors"]:
            print(f"  - {err}")

    print("\n" + "=" * 70)
    print(f"Pipeline complete. Run ID: {run_id}")
    print("=" * 70 + "\n")


def review_journal():
    """Review expired trades and update the memory bank."""
    print("\n" + "=" * 70)
    print("  S&P MARKETS - TRADE JOURNAL REVIEW")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70 + "\n")

    journal = JournalAgent()
    results = journal.review_expired_trades()

    if not results:
        print("No expired trades to review.\n")
        return

    print(f"Reviewed {len(results)} expired trades:\n")
    print(f"  {'Symbol':<12} {'Dir':>5} {'Entry':>8} {'Target':>8} {'Best':>8} {'BestP&L':>8} {'Status':>8}")
    print("  " + "-" * 65)

    hits = 0
    for r in results:
        status = "HIT" if r.target_hit else "MISS"
        if r.target_hit:
            hits += 1
        print(
            f"  {r.symbol:<12} {r.direction:>5} {r.entry_price:>8.2f} "
            f"{r.target_price:>8.2f} {r.best_exit_price:>8.2f} "
            f"{r.best_pnl_pct:>+7.2f}% {status:>8}"
        )

    print(f"\n  Hit rate: {hits}/{len(results)} ({hits/len(results)*100:.0f}%)")
    print("\n  Memory bank updated for DM + RM learning.\n")


def main():
    parser = argparse.ArgumentParser(
        description="S&P Markets - Multi-Agent Trading Firm",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  run       Execute the full analysis pipeline (news -> trades)
  review    Review expired trades, calculate P&L, update memory bank
        """,
    )
    parser.add_argument(
        "command",
        choices=["run", "review"],
        help="Command to execute",
    )
    args = parser.parse_args()

    setup_logging()

    if args.command == "run":
        run_pipeline()
    elif args.command == "review":
        review_journal()


if __name__ == "__main__":
    main()
