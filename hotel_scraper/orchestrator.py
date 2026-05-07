"""Main orchestrator. Now delegates to the LangGraph pipeline.

The public API (scrape function) is unchanged so the CLI (main.py) keeps working.
"""

from models.hotel_data import Hotel


def scrape(url: str, output_dir: str = "./output", use_llm: bool = False) -> Hotel:
    """Full scraping pipeline for a single hotel URL (delegates to LangGraph).

    Args:
        url: The hotel website URL.
        output_dir: Root directory for all output files.
        use_llm: Whether to activate LLM fallback / autonomous navigation.

    Returns:
        Populated Hotel object.
    """
    from graph.graph import run_graph
    return run_graph(url=url, output_dir=output_dir, use_llm=use_llm)
