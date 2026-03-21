import logging
from datetime import date

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage

from config.settings import settings
from models.analysis import StockAnalysis
from models.market_data import MarketContext
from models.decision import DMOutput
from storage.memory_bank import MemoryBank

logger = logging.getLogger(__name__)


class DecisionMaker:
    """Receives Bull & Bear cases, makes unbiased trade decisions using Opus 4.6."""

    def __init__(self):
        self.llm = ChatAnthropic(
            model=settings.OPUS_MODEL,
            api_key=settings.ANTHROPIC_API_KEY,
            temperature=0.1,
            max_tokens=4096,
        )
        self.memory_bank = MemoryBank()

    def decide(
        self,
        analyses: list[StockAnalysis],
        market_context: MarketContext,
        memory: dict,
    ) -> DMOutput:
        logger.info(f"Making decisions for {len(analyses)} stocks...")

        structured_llm = self.llm.with_structured_output(DMOutput)
        today = date.today()
        day_name = today.strftime("%A")

        system_prompt = f"""You are the Chief Decision Maker at a systematic trading firm.
Today is {today.isoformat()} ({day_name}).

You receive both BULL and BEAR cases for each stock from independent analysts.
Your job: make an UNBIASED decision by weighing both sides objectively.

DECISION RULES:
- For each stock, choose LONG, SHORT, or IGNORE
- IGNORE if bull/bear confidence is within 0.15 of each other (too balanced)
- Minimum confidence of 0.6 to recommend a trade
- Max timeframe: 5 trading days
- Higher conviction = can use tighter timeframe
- Entry price should be near the current market price (latest close)
- Target should be realistic for the timeframe (don't expect 10% in 2 days for large caps)

SEASONALITY & TIMING:
- Monday: often gap-up/down from weekend news
- Tuesday-Thursday: strongest trading days
- Friday: position squaring before weekend, lower conviction
- Month-end: FII/DII rebalancing flows
- Expiry weeks (last Thursday): increased volatility
- Budget/RBI policy days: avoid unless directly positioned

WEIGHTING GUIDANCE:
- News-driven catalyst with fundamental backing: highest conviction
- Pure technical setup: moderate conviction
- Macro-only thesis: lower conviction unless very strong
- Assign bull_weight and bear_weight (0.0-1.0) reflecting how compelling each case is

PAST PERFORMANCE (use this to calibrate):
{self._format_memory(memory)}

If historical hit rate is low, be more conservative with confidence scores.
If you tend to overestimate bullish moves, adjust accordingly."""

        analyses_text = self._format_analyses(analyses)

        human_msg = f"""MARKET CONTEXT:
Nifty 50: {market_context.nifty50.value} ({market_context.nifty50.change_pct:+.2f}%)
Bank Nifty: {market_context.banknifty.value} ({market_context.banknifty.change_pct:+.2f}%)
India VIX: {market_context.vix.value} ({market_context.vix.change_pct:+.2f}%)

STOCK ANALYSES (Bull & Bear cases):
{analyses_text}

Make your decisions for each stock. Be decisive but disciplined."""

        result = structured_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_msg),
        ])

        # Ensure metadata is set
        result.current_date = today
        result.day_of_week = day_name

        active_trades = [d for d in result.decisions if d.direction.value != "IGNORE"]
        ignored = len(result.decisions) - len(active_trades)
        logger.info(
            f"DM decisions: {len(active_trades)} active trades, {ignored} ignored. "
            f"Outlook: {result.market_outlook}"
        )
        return result

    def load_memory(self) -> dict:
        return self.memory_bank.get_dm_feedback()

    def _format_analyses(self, analyses: list[StockAnalysis]) -> str:
        parts = []
        for analysis in analyses:
            parts.append(f"\n{'='*60}")
            parts.append(f"STOCK: {analysis.symbol}")

            if analysis.bull_case:
                bc = analysis.bull_case
                parts.append(f"\n  BULL CASE (confidence: {bc.overall_confidence:.2f}):")
                parts.append(f"  Catalyst: {bc.catalyst}")
                parts.append(f"  Target: {bc.target_price}")
                parts.append(f"  Summary: {bc.summary}")
                for arg in bc.arguments:
                    parts.append(f"    [{arg.factor}] {arg.argument} (weight: {arg.weight:.2f})")
                    parts.append(f"      Data: {arg.supporting_data}")

            if analysis.bear_case:
                bc = analysis.bear_case
                parts.append(f"\n  BEAR CASE (confidence: {bc.overall_confidence:.2f}):")
                parts.append(f"  Risk Factor: {bc.risk_factor}")
                parts.append(f"  Downside Target: {bc.downside_target}")
                parts.append(f"  Summary: {bc.summary}")
                for arg in bc.arguments:
                    parts.append(f"    [{arg.factor}] {arg.argument} (weight: {arg.weight:.2f})")
                    parts.append(f"      Data: {arg.supporting_data}")

        return "\n".join(parts)

    def _format_memory(self, memory: dict) -> str:
        if not memory or memory.get("total_trades", 0) == 0:
            return "No historical data yet. This is the first run."

        parts = [
            f"Total past trades: {memory['total_trades']}",
            f"Hit rate (target reached): {memory.get('hit_rate', 0):.1%}",
            f"Average best P&L: {memory.get('avg_best_pnl', 0):.2f}%",
        ]

        recent = memory.get("recent_reviews", [])
        if recent:
            parts.append(f"\nLast {len(recent)} trade outcomes:")
            for r in recent[-5:]:
                symbol = r.get("symbol", "?")
                direction = r.get("direction", "?")
                best_pnl = r.get("best_pnl_pct", 0)
                target_hit = r.get("target_hit", False)
                status = "HIT" if target_hit else "MISS"
                parts.append(f"  {symbol} {direction}: best {best_pnl:+.2f}% [{status}]")

        return "\n".join(parts)
