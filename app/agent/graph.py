from langgraph.graph import END, START, StateGraph

from app.agent.nodes import (
    BriefingState,
    completeness_check_node,
    ingest_node,
    memory_filter_node,
    route_completeness,
    score_filter_node,
    store_deliver_node,
    summarize_node,
    synthesize_node,
)

graph_builder = StateGraph(BriefingState)

# Add nodes
graph_builder.add_node("ingest", ingest_node)
graph_builder.add_node("memory_filter", memory_filter_node)
graph_builder.add_node("score_filter", score_filter_node)
graph_builder.add_node("completeness_check", completeness_check_node)
graph_builder.add_node("summarize", summarize_node)
graph_builder.add_node("synthesize", synthesize_node)
graph_builder.add_node("store_deliver", store_deliver_node)

# Wire edges
graph_builder.add_edge(START, "ingest")
graph_builder.add_edge("ingest", "memory_filter")
graph_builder.add_edge("memory_filter", "score_filter")
graph_builder.add_edge("score_filter", "completeness_check")
graph_builder.add_conditional_edges(
    "completeness_check",
    route_completeness,
    {"retry": "ingest", "continue": "summarize"},
)
graph_builder.add_edge("summarize", "synthesize")
graph_builder.add_edge("synthesize", "store_deliver")
graph_builder.add_edge("store_deliver", END)

briefing_graph = graph_builder.compile()
