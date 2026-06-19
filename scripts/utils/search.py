import asyncio
from ddgs import DDGS
import logging
from scripts.main import smart_title_case

import requests
from lxml import html
import json

async def search_images(query: str, max_results: int = 3, safesearch: str = 'on'):
    """
    Performs an image search using Bing Images with custom safesearch mapping.
    Uses requests inside asyncio.to_thread to bypass library TLS/fingerprint blocks.
    """
    def _fetch():
        url = "https://www.bing.com/images/async"
        
        # Map safesearch value
        adlt_val = "STRICT"
        if safesearch.lower() == 'off':
            adlt_val = "OFF"
        elif safesearch.lower() == 'moderate':
            adlt_val = "DEMOTE"
            
        payload = {
            "q": query,
            "async": "1",
            "first": "1",
            "count": str(max(max_results, 35)),
            "adlt": adlt_val.lower()
        }
        cookies = {
            "SRCHHPGUSR": f"ADLT={adlt_val}"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        r = requests.get(url, params=payload, headers=headers, cookies=cookies, timeout=10)
        r.raise_for_status()
        return r.text

    try:
        html_text = await asyncio.to_thread(_fetch)
        tree = html.fromstring(html_text)
        items = tree.xpath("//div[./div[@class='imgpt']/a[@m] and ./div[@class='infopt']]")
        
        results = []
        for item in items[:max_results]:
            metadata = item.xpath(".//a[@class='iusc']/@m")
            if metadata:
                try:
                    m = json.loads(metadata[0])
                    results.append({
                        "title": m.get("t", "Gambar"),
                        "image": m.get("murl", ""),
                        "thumbnail": m.get("turl", ""),
                        "url": m.get("purl", "")
                    })
                except Exception:
                    continue
        return results
    except Exception as e:
        logging.error(f"Error in custom image search: {e}")
        return []

async def search_web(query: str, max_results: int = 5, safesearch: str = 'on'):
    """
    Performs a web search using DuckDuckGo and returns snippets and links.
    """
    try:
        results = []
        with DDGS() as ddgs:
            # Using as_iter to get results in a more modern way if needed, 
            # but text() is the standard for general search.
            search_results = ddgs.text(query, max_results=max_results, safesearch=safesearch)
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
