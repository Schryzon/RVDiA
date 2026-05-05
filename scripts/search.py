import asyncio
from ddgs import DDGS
import logging

async def search_web(query: str, max_results: int = 5):
    """
    Performs a web search using DuckDuckGo and returns snippets and links.
    """
    try:
        results = []
        with DDGS() as ddgs:
            # Using as_iter to get results in a more modern way if needed, 
            # but text() is the standard for general search.
            search_results = ddgs.text(query, max_results=max_results)
            for r in search_results:
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "link": r.get("href", "")
                })
        return results
    except Exception as e:
        logging.error(f"Error in web search: {e}")
        return []

def format_search_results(results):
    """Formats search results for the LLM context."""
    if not results:
        return "No relevant search results found."
    
    formatted = "Web Search Results:\n"
    for i, res in enumerate(results, 1):
        formatted += f"{i}. {res['title']}\n   Snippet: {res['snippet']}\n   Link: {res['link']}\n"
    return formatted

# Quick test if run directly
if __name__ == "__main__":
    import json
    async def main():
        query = "berita terbaru hari ini di indonesia"
        results = await search_web(query)
        print(json.dumps(results, indent=2))
    
    asyncio.run(main())
