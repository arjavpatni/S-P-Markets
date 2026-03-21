from models.state import PipelineState


def should_continue_after_correlation(state: PipelineState) -> str:
    """If no affected stocks found, end the pipeline early."""
    affected = state.get("affected_symbols", [])
    if not affected:
        return "stop"
    return "continue"
