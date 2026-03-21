import uuid
import logging
from datetime import date, timedelta

from data.yfinance_client import YFinanceClient
from models.news import NewsBundle
from models.correlation import CorrelationResult
from models.decision import DMOutput
from models.risk import RMOutput
from models.journal import TradeRecord, ReviewResult
from storage.trade_journal import TradeJournalStore
from storage.memory_bank import MemoryBank

logger = logging.getLogger(__name__)


class JournalAgent:
    """Records trades, reviews expired ones, and updates the memory bank for learning."""

    def __init__(self):
        self.store = TradeJournalStore()
        self.memory = MemoryBank()
        self.yf_client = YFinanceClient()

    def record(
        self,
        dm_output: DMOutput,
        rm_output: RMOutput,
        news: NewsBundle,
        correlation: CorrelationResult,
        run_id: str,
    ):
        """Write all approved trades to disk as JSON."""
        logger.info(f"Recording {len(rm_output.approved_trades)} trades...")

        for trade in rm_output.approved_trades:
            entry_date = date.today()
            expiry_date = self._add_trading_days(entry_date, trade.timeframe_days)

            dm_confidence = self._get_dm_confidence(dm_output, trade.symbol)

            record = TradeRecord(
                id=str(uuid.uuid4()),
                symbol=trade.symbol,
                direction=trade.direction,
                entry_price=trade.entry_price,
                target_price=trade.target_price,
                stop_loss=trade.stop_loss,
                quantity=trade.quantity,
                timeframe_days=trade.timeframe_days,
                entry_date=entry_date,
                expiry_date=expiry_date,
                dm_confidence=dm_confidence,
                risk_notes=trade.risk_notes,
            )
            self.store.save_trade(record)
            logger.info(
                f"  Recorded: {trade.direction} {trade.symbol} "
                f"qty={trade.quantity} entry={trade.entry_price} "
                f"target={trade.target_price} SL={trade.stop_loss}"
            )

    def review_expired_trades(self) -> list[ReviewResult]:
        """Check trades past their expiry, fetch real prices, calculate P&L."""
        expired = self.store.get_expired_trades()
        if not expired:
            logger.info("No expired trades to review.")
            return []

        logger.info(f"Reviewing {len(expired)} expired trades...")
        results = []

        for trade in expired:
            try:
                ohlcv = self.yf_client.get_ohlcv(
                    trade.symbol,
                    start=trade.entry_date,
                    end=trade.expiry_date,
                )
                review = self._evaluate_trade(trade, ohlcv)
                results.append(review)
                self.store.mark_reviewed(trade.id, review)
                logger.info(
                    f"  {trade.symbol} {trade.direction}: "
                    f"best P&L={review.best_pnl_pct:+.2f}% "
                    f"target={'HIT' if review.target_hit else 'MISS'} "
                    f"stop={'HIT' if review.stop_hit else 'SAFE'}"
                )
            except Exception as e:
                logger.error(f"Failed to review trade {trade.id} ({trade.symbol}): {e}")

        # Update memory bank for learning
        if results:
            self.memory.update_dm_feedback(results)
            self.memory.update_rm_feedback(results)
            logger.info(f"Memory bank updated with {len(results)} reviews.")

        return results

    def _evaluate_trade(self, trade: TradeRecord, ohlcv) -> ReviewResult:
        """Calculate best possible P&L within the trading window."""
        highs = [bar.high for bar in ohlcv.bars]
        lows = [bar.low for bar in ohlcv.bars]

        actual_high = max(highs) if highs else trade.entry_price
        actual_low = min(lows) if lows else trade.entry_price

        if trade.direction == "LONG":
            best_exit = actual_high
            best_pnl_pct = (best_exit - trade.entry_price) / trade.entry_price * 100
            worst_pnl_pct = (actual_low - trade.entry_price) / trade.entry_price * 100
            target_hit = actual_high >= trade.target_price
            stop_hit = actual_low <= trade.stop_loss
        else:  # SHORT
            best_exit = actual_low
            best_pnl_pct = (trade.entry_price - best_exit) / trade.entry_price * 100
            worst_pnl_pct = (trade.entry_price - actual_high) / trade.entry_price * 100
            target_hit = actual_low <= trade.target_price
            stop_hit = actual_high >= trade.stop_loss

        return ReviewResult(
            trade_id=trade.id,
            symbol=trade.symbol,
            direction=trade.direction,
            entry_price=trade.entry_price,
            target_price=trade.target_price,
            actual_high=round(actual_high, 2),
            actual_low=round(actual_low, 2),
            best_exit_price=round(best_exit, 2),
            best_pnl_pct=round(best_pnl_pct, 2),
            worst_pnl_pct=round(worst_pnl_pct, 2),
            target_hit=target_hit,
            stop_hit=stop_hit,
            review_date=date.today(),
        )

    def _get_dm_confidence(self, dm_output: DMOutput, symbol: str) -> float:
        for d in dm_output.decisions:
            if d.symbol == symbol:
                return d.confidence
        return 0.0

    @staticmethod
    def _add_trading_days(start: date, trading_days: int) -> date:
        """Add N trading days (skip weekends) to a date."""
        current = start
        added = 0
        while added < trading_days:
            current += timedelta(days=1)
            if current.weekday() < 5:  # Mon-Fri
                added += 1
        return current
