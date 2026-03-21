import logging
from collections import defaultdict

from config.settings import settings
from models.decision import DMOutput
from models.market_data import OHLCVData, MarketContext
from models.risk import RiskVerdict, ApprovedTrade, RMOutput
from storage.memory_bank import MemoryBank

logger = logging.getLogger(__name__)


class RiskManager:
    """Rule-based risk management with position sizing, stop-loss, and veto power."""

    def __init__(self):
        self.memory_bank = MemoryBank()
        self.capital = settings.DEFAULT_CAPITAL
        self.max_single_risk_pct = settings.MAX_SINGLE_TRADE_RISK_PCT
        self.max_portfolio_risk_pct = settings.MAX_PORTFOLIO_RISK_PCT
        self.vix_high = settings.VIX_HIGH_THRESHOLD
        self.vix_extreme = settings.VIX_EXTREME_THRESHOLD
        self.min_rr = settings.MIN_RISK_REWARD
        self.atr_mult = settings.ATR_MULTIPLIER

    def assess(
        self,
        decisions: DMOutput,
        market_context: MarketContext,
        ohlcv: dict[str, OHLCVData],
        memory: dict,
    ) -> RMOutput:
        logger.info("Risk Manager assessing trades...")

        vix_level = market_context.vix.value
        vix_assessment = self._assess_vix(vix_level)

        # VETO: No new trades if VIX is extreme
        if vix_level > self.vix_extreme:
            logger.warning(f"VIX at {vix_level:.1f} - EXTREME. Vetoing all trades.")
            return RMOutput(
                approved_trades=[],
                rejected_trades=[{"symbol": "ALL", "reason": f"VIX {vix_level:.1f} > {self.vix_extreme} extreme threshold"}],
                portfolio_risk_score=0.0,
                vix_assessment=vix_assessment,
                total_capital_at_risk_pct=0.0,
            )

        approved = []
        rejected = []
        total_risk = 0.0

        for decision in decisions.decisions:
            if decision.direction.value == "IGNORE":
                continue

            symbol = decision.symbol
            if symbol not in ohlcv or not ohlcv[symbol].bars:
                rejected.append({"symbol": symbol, "reason": "No OHLCV data available"})
                continue

            # Calculate ATR for stop-loss
            atr = self._calculate_atr(ohlcv[symbol])
            if atr <= 0:
                rejected.append({"symbol": symbol, "reason": "ATR calculation failed"})
                continue

            # Compute stop-loss
            stop_loss = self._compute_stop_loss(decision, atr)

            # Risk per share
            risk_per_share = abs(decision.entry_price - stop_loss)
            if risk_per_share <= 0:
                rejected.append({"symbol": symbol, "reason": "Invalid stop-loss distance"})
                continue

            # Position sizing: max risk per trade
            max_risk_amount = self.capital * (self.max_single_risk_pct / 100)
            quantity = int(max_risk_amount / risk_per_share)

            # Reduce size if VIX is elevated
            if vix_level > self.vix_high:
                quantity = int(quantity * 0.5)
                logger.info(f"VIX elevated ({vix_level:.1f}), halving position size for {symbol}")

            # Check risk-reward ratio
            reward_per_share = abs(decision.target_price - decision.entry_price)
            rr_ratio = reward_per_share / risk_per_share if risk_per_share > 0 else 0

            if rr_ratio < self.min_rr:
                rejected.append({
                    "symbol": symbol,
                    "reason": f"Risk-reward {rr_ratio:.2f} < {self.min_rr} minimum",
                })
                continue

            if quantity == 0:
                rejected.append({"symbol": symbol, "reason": "Position size rounds to zero"})
                continue

            # Check portfolio-level risk limit
            trade_risk = risk_per_share * quantity
            if total_risk + trade_risk > self.capital * (self.max_portfolio_risk_pct / 100):
                rejected.append({
                    "symbol": symbol,
                    "reason": f"Would exceed portfolio risk limit ({self.max_portfolio_risk_pct}%)",
                })
                continue

            total_risk += trade_risk

            approved.append(ApprovedTrade(
                symbol=symbol,
                direction=decision.direction.value,
                entry_price=decision.entry_price,
                target_price=decision.target_price,
                stop_loss=round(stop_loss, 2),
                quantity=quantity,
                risk_reward_ratio=round(rr_ratio, 2),
                max_loss_amount=round(trade_risk, 2),
                timeframe_days=decision.timeframe_days,
                verdict=RiskVerdict.APPROVED,
                risk_notes=f"ATR={atr:.2f}, SL={self.atr_mult}xATR. VIX={vix_level:.1f}",
            ))

        # Check sector correlation
        approved = self._check_sector_correlation(approved, ohlcv)

        portfolio_risk_pct = (total_risk / self.capital * 100) if self.capital > 0 else 0

        logger.info(
            f"RM result: {len(approved)} approved, {len(rejected)} rejected. "
            f"Portfolio risk: {portfolio_risk_pct:.2f}%"
        )

        return RMOutput(
            approved_trades=approved,
            rejected_trades=rejected,
            portfolio_risk_score=round(portfolio_risk_pct / self.max_portfolio_risk_pct, 2),
            vix_assessment=vix_assessment,
            total_capital_at_risk_pct=round(portfolio_risk_pct, 2),
        )

    def load_memory(self) -> dict:
        return self.memory_bank.get_rm_feedback()

    def _calculate_atr(self, ohlcv: OHLCVData, period: int = 14) -> float:
        """Calculate Average True Range from OHLCV bars."""
        bars = ohlcv.bars
        if len(bars) < 2:
            return 0.0

        true_ranges = []
        for i in range(1, len(bars)):
            high_low = bars[i].high - bars[i].low
            high_prev_close = abs(bars[i].high - bars[i - 1].close)
            low_prev_close = abs(bars[i].low - bars[i - 1].close)
            true_ranges.append(max(high_low, high_prev_close, low_prev_close))

        if not true_ranges:
            return 0.0

        # Use the last `period` true ranges
        recent_trs = true_ranges[-period:]
        return sum(recent_trs) / len(recent_trs)

    def _compute_stop_loss(self, decision, atr: float) -> float:
        """Stop loss = entry +/- ATR_MULTIPLIER * ATR depending on direction."""
        if decision.direction.value == "LONG":
            return decision.entry_price - (self.atr_mult * atr)
        else:
            return decision.entry_price + (self.atr_mult * atr)

    def _assess_vix(self, vix: float) -> str:
        if vix > self.vix_extreme:
            return f"EXTREME ({vix:.1f}) - No new positions"
        elif vix > self.vix_high:
            return f"HIGH ({vix:.1f}) - Reduced position sizes"
        elif vix > 15:
            return f"MODERATE ({vix:.1f}) - Normal trading"
        else:
            return f"LOW ({vix:.1f}) - Favorable conditions"

    def _check_sector_correlation(
        self, trades: list[ApprovedTrade], ohlcv: dict[str, OHLCVData]
    ) -> list[ApprovedTrade]:
        """Reduce position sizes if too many trades in the same direction for correlated stocks."""
        # Group by direction
        direction_groups = defaultdict(list)
        for trade in trades:
            direction_groups[trade.direction].append(trade)

        result = []
        for direction, group in direction_groups.items():
            if len(group) > 3:
                logger.warning(
                    f"{len(group)} trades all {direction} - reducing sizes by 30% for diversification"
                )
                for trade in group:
                    resized = trade.model_copy(update={
                        "quantity": max(1, int(trade.quantity * 0.7)),
                        "verdict": RiskVerdict.RESIZED,
                        "risk_notes": trade.risk_notes + " | Resized: sector correlation",
                    })
                    result.append(resized)
            else:
                result.extend(group)

        return result
