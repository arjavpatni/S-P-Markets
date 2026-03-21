from langgraph.graph import START, END, StateGraph

from models.state import PipelineState
from graph.nodes import (
    fetch_news_node,
    correlate_news_node,
    fetch_market_data_node,
    bull_analyst_node,
    bear_analyst_node,
    decision_maker_node,
    risk_manager_node,
    record_trades_node,
)
from graph.edges import should_continue_after_correlation


def build_workflow() -> StateGraph:
    """Build the LangGraph pipeline for the trading firm.

    Flow:
        START → fetch_news → correlate_news → [conditional]
              → fetch_market_data → [fan-out: bull + bear analysts]
              → [fan-in] → decision_maker → risk_manager
              → record_trades → END
    """
    graph = StateGraph(PipelineState)

    # Add all nodes
    graph.add_node("fetch_news", fetch_news_node)
    graph.add_node("correlate_news", correlate_news_node)
    graph.add_node("fetch_market_data", fetch_market_data_node)
    graph.add_node("bull_analyst", bull_analyst_node)
    graph.add_node("bear_analyst", bear_analyst_node)
    graph.add_node("decision_maker", decision_maker_node)
    graph.add_node("risk_manager", risk_manager_node)
    graph.add_node("record_trades", record_trades_node)

    # Edge: START → fetch_news → correlate_news
    graph.add_edge(START, "fetch_news")
    graph.add_edge("fetch_news", "correlate_news")

    # Conditional: skip pipeline if no affected stocks found
    graph.add_conditional_edges(
        "correlate_news",
        should_continue_after_correlation,
        {
            "continue": "fetch_market_data",
            "stop": END,
        },
    )

    # Fan-out: market data feeds both analysts in parallel
    graph.add_edge("fetch_market_data", "bull_analyst")
    graph.add_edge("fetch_market_data", "bear_analyst")

    # Fan-in: both analysts must complete before DM runs
    graph.add_edge("bull_analyst", "decision_maker")
    graph.add_edge("bear_analyst", "decision_maker")

    # Sequential: DM → RM → Journal → END
    graph.add_edge("decision_maker", "risk_manager")
    graph.add_edge("risk_manager", "record_trades")
    graph.add_edge("record_trades", END)

    return graph.compile()
