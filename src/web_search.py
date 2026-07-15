import urllib.request
import urllib.parse
import re

def perform_web_search(query: str, num_results: int = 3) -> str:
    """
    Performs a lightweight web search using DuckDuckGo HTML version.
    Returns a formatted string of search results.
    """
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    req = urllib.request.Request(
        url, 
        data=None, 
        headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode('utf-8')
            
        # Extract snippets using regex
        snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
        titles = re.findall(r'<h2 class="result__title">.*?<a[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
        
        results = []
        for i in range(min(num_results, len(snippets))):
            title = re.sub(r'<[^>]+>', '', titles[i]).strip() if i < len(titles) else f"Result {i+1}"
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip()
            results.append(f"[{title}]\n{snippet}")
            
        if not results:
            return "No search results found."
            
        return "\n\n".join(results)
    except Exception as e:
        return f"Web search failed: {str(e)}"
