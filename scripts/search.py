import asyncio
from ddgs import DDGS
import logging
from scripts.main import smart_title_case

async def search_images(query: str, max_results: int = 3):
    """
    Performs an image search using DuckDuckGo and returns image links.
    (Non-NSFW by default with safesearch='on')
    """
    try:
        results = []
        with DDGS() as ddgs:
            search_results = ddgs.images(query, max_results=max_results, safesearch='on')
            for r in search_results:
                results.append({
                    "title": r.get("title", ""),
                    "image": r.get("image", ""),
                    "thumbnail": r.get("thumbnail", ""),
                    "url": r.get("url", "")
                })
        return results
    except Exception as e:
        logging.error(f"Error in image search: {e}")
        return []

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
        # Use smart_title_case for search result titles
        title = smart_title_case(res['title'])
        formatted += f"{i}. {title}\n   Snippet: {res['snippet']}\n   Link: {res['link']}\n"
    return formatted

# Quick test if run directly
if __name__ == "__main__":
    import json
    async def main():
        query = "berita terbaru hari ini di indonesia"
        results = await search_web(query)
        print(json.dumps(results, indent=2))
    
    asyncio.run(main())
