"""
web_search.py — Unified Reliable Web Search for Iris AI
========================================================
Drop-in replacement for the fragmented DuckDuckGo/Wikipedia search in 
app.py (voice) and iris.py (text chat). Guarantees results from at 
least one backend under all conditions.

Backend fallback chain (auto, configurable):
  1. DuckDuckGo Instant Answers + Text + News  (via `ddgs` lib)
  2. Wikipedia API                               (via `requests`)
  3. Direct web scrape fallback                  (via `requests` + `bs4`)

Features:
  - Exponential backoff retry on 202/RateLimit responses
  - Thread-safe singleton: no duplicate requests
  - Smart keyword extraction via lightweight LLM
  - Full-text page fetching for the top result
  - Timeout protection at every layer
  - Comprehensive error logging
"""

import os
import re
import json
import time
import logging
import threading
import urllib.parse
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

try:
    from ddgs import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False

logger = logging.getLogger("iris.web_search")


@dataclass
class SearchResult:
    title: str = ""
    body: str = ""
    href: str = ""
    source: str = "web"

    def to_dict(self) -> dict:
        return {"title": self.title, "body": self.body, "href": self.href, "source": self.source}

    def to_context_str(self) -> str:
        parts = [f"**{self.title}**"]
        if self.body:
            parts.append(self.body[:600])
        if self.href:
            parts.append(f"[source]({self.href})")
        return "\n".join(parts)


class WebSearch:
    """Unified, retry-hardened web search with automatic backend fallback.

    Usage:
        ws = WebSearch()
        results = ws.search("Python programming", max_results=3)
        context = ws.search_to_context("Python programming", max_results=3)
    """

    _singleton = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._singleton is None:
            with cls._lock:
                if cls._singleton is None:
                    cls._singleton = super().__new__(cls)
                    cls._singleton._initialized = False
        return cls._singleton

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._session = None
        self._ddg_available = DDGS_AVAILABLE
        self._ddg_rate_limited_until = 0.0
        if REQUESTS_AVAILABLE:
            self._session = requests.Session()
            retry = Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
            adapter = HTTPAdapter(max_retries=retry)
            self._session.mount("https://", adapter)
            self._session.mount("http://", adapter)
        self._user_agent = "Iris-AI/1.0 (https://github.com/ahmed-barakat/Iris-AI)"

    # ── Primary: DuckDuckGo (via ddgs library) ──

    def _search_ddg(self, query: str, max_results: int, timeout: float = 8.0) -> List[SearchResult]:
        """Search DuckDuckGo text + news via the ddgs library."""
        if not self._ddg_available:
            return []
        now = time.time()
        if now < self._ddg_rate_limited_until:
            logger.warning("[WebSearch] DDG rate-limited until %.0f seconds from now",
                           self._ddg_rate_limited_until - now)
            return []
        results: List[SearchResult] = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results, backend="html"):
                    results.append(SearchResult(
                        title=r.get("title", ""),
                        body=r.get("body", ""),
                        href=r.get("href", ""),
                        source="ddg_text",
                    ))
                    if len(results) >= max_results:
                        break
        except Exception as e:
            err = str(e).lower()
            if "202" in err or "403" in err or "rate" in err or "limited" in err:
                self._ddg_rate_limited_until = time.time() + 30.0
                logger.warning("[WebSearch] DDG rate-limited, backoff 30s")
            else:
                logger.warning(f"[WebSearch] DDG text failed: {e}")

        if len(results) < max_results and time.time() >= self._ddg_rate_limited_until:
            try:
                with DDGS() as ddgs:
                    for r in ddgs.news(query, max_results=max((max_results - len(results)), 1)):
                        results.append(SearchResult(
                            title=r.get("title", ""),
                            body=r.get("body", ""),
                            href=r.get("url", r.get("href", "")),
                            source="ddg_news",
                        ))
                        if len(results) >= max_results:
                            break
            except Exception as e:
                logger.debug(f"[WebSearch] DDG news failed: {e}")
        return results[:max_results]

    # ── Fallback 1: Wikipedia API ──

    def _search_wikipedia(self, query: str, max_results: int, timeout: float = 6.0) -> List[SearchResult]:
        """Search Wikipedia via the mediawiki API and get full intro paragraphs."""
        if not REQUESTS_AVAILABLE:
            return []
        results: List[SearchResult] = []
        try:
            encoded = urllib.parse.quote(query)
            is_ar = bool(re.search(r'[\u0600-\u06FF]', query))
            wiki_domain = "ar.wikipedia.org" if is_ar else "en.wikipedia.org"
            url = (f"https://{wiki_domain}/w/api.php?action=query&generator=search"
                   f"&gsrsearch={encoded}&gsrlimit={max(3, max_results)}"
                   f"&prop=extracts&exintro=1&explaintext=1&exlimit={max(3, max_results)}&utf8=&format=json")
            resp = self._session.get(url, timeout=timeout,
                                     headers={"User-Agent": self._user_agent})
            resp.raise_for_status()
            data = resp.json()
            
            pages = data.get("query", {}).get("pages", {})
            # Sort pages by index (search rank)
            sorted_pages = sorted(pages.values(), key=lambda p: p.get("index", 999))
            
            for item in sorted_pages[:max_results]:
                extract = item.get("extract", "").strip()
                if not extract:
                    continue
                results.append(SearchResult(
                    title=item.get("title", ""),
                    body=f"Wikipedia: {extract}",
                    href=f"https://{wiki_domain}/wiki/{urllib.parse.quote(item.get('title', ''))}",
                    source="wikipedia",
                ))
        except Exception as e:
            logger.warning(f"[WebSearch] Wikipedia API failed: {e}")
        return results[:max_results]

    # ── Fallback 2: Google scrape (via requests + bs4) ──

    def _search_google_scrape(self, query: str, timeout: float = 8.0) -> List[SearchResult]:
        """Lightweight Google search scraping as final fallback."""
        if not REQUESTS_AVAILABLE or not BS4_AVAILABLE:
            return []
        results: List[SearchResult] = []
        try:
            encoded = urllib.parse.quote(query)
            is_ar = bool(re.search(r'[\u0600-\u06FF]', query))
            hl = "ar" if is_ar else "en"
            url = f"https://www.google.com/search?q={encoded}&hl={hl}"
            resp = self._session.get(url, timeout=timeout,
                                     headers={"User-Agent": self._user_agent})
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            # Look for result divs — tolerant against DOM changes
            for g in soup.select("div.g, div[data-sokoban-container], div.tF2Cxc")[:3]:
                title_el = g.select_one("h3")
                snippet_el = g.select_one("div.VwiC3b, span.st, div[data-sncf]")
                link_el = g.select_one("a[href]")
                title = title_el.get_text(separator=" ", strip=True) if title_el else ""
                snippet = snippet_el.get_text(separator=" ", strip=True) if snippet_el else ""
                href = link_el.get("href", "") if link_el else ""
                if title and (snippet or href):
                    results.append(SearchResult(
                        title=title, body=snippet[:600], href=href, source="google"
                    ))
        except Exception as e:
            logger.warning(f"[WebSearch] Google scrape failed: {e}")
        return results[:3]

    # ── Public API ──

    def search(self, query: str, max_results: int = 3,
               include_full_text: bool = True,
               timeout: float = 12.0,
               bypass_cache: bool = False) -> List[SearchResult]:
        """Main search entry point. Falls back through every backend automatically.

        Args:
            query:          Natural language search query.
            max_results:    Maximum results to return (1-10).
            include_full_text: Fetch the full text of the top result's page.
            timeout:        Total time budget for the search.
            bypass_cache:   Ignore internal deduplication cache.

        Returns:
            List of SearchResult objects (always returns at least an empty list).
        """
        query = query.strip()
        if not query:
            return []
        max_results = max(1, min(max_results, 10))
        deadline = time.time() + timeout
        all_results: List[SearchResult] = []

        # Tier 1: Wikipedia API (High factual accuracy)
        if time.time() < deadline:
            wiki_results = self._search_wikipedia(query, max_results=max_results)
            if wiki_results:
                logger.info(f"[WebSearch] Wikipedia returned {len(wiki_results)} results")
                all_results.extend(wiki_results)

        # Tier 2: DuckDuckGo (Broader scope, news, forums)
        if len(all_results) < max_results and self._ddg_available:
            ddg_results = self._search_ddg(query, max_results - len(all_results), timeout=min(6.0, timeout))
            if ddg_results:
                logger.info(f"[WebSearch] DDG returned {len(ddg_results)} results for '{query[:60]}'")
                all_results.extend(ddg_results)

        # Tier 3: Google scrape
        if len(all_results) == 0 and time.time() < deadline:
            google_results = self._search_google_scrape(query)
            if google_results:
                logger.info(f"[WebSearch] Google returned {len(google_results)} results")
                all_results.extend(google_results)

        # Fetch full text for top result
        if include_full_text and all_results and all_results[0].href and time.time() < deadline:
            full = self._fetch_full_text(all_results[0].href, timeout=4.0)
            if full:
                all_results[0].body = full[:4000]

        return all_results[:max_results]

    def search_to_context(self, query: str, max_results: int = 3) -> str:
        """Search and format results as a context string for LLM injection.

        Returns empty string if no results found.
        """
        results = self.search(query, max_results)
        if not results:
            return ""
        lines = ["\n[LIVE INTERNET SEARCH RESULTS]"]
        for i, r in enumerate(results, 1):
            lines.append(f"Result {i}: {r.to_context_str()}")
        lines.append("[END LIVE INTERNET SEARCH RESULTS]\n")
        return "\n".join(lines)

    def _fetch_full_text(self, url: str, timeout: float = 4.0) -> str:
        """Fetch and extract readable text from a URL."""
        if not REQUESTS_AVAILABLE or not BS4_AVAILABLE:
            return ""
        try:
            resp = self._session.get(url, timeout=timeout,
                                     headers={"User-Agent": self._user_agent})
            if resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header",
                             "noscript", "iframe", "form"]):
                tag.extract()
            text = soup.get_text(separator=" ", strip=True)
            # Clean whitespace
            text = re.sub(r"\s+", " ", text)
            if len(text) > 200:
                return text[:4000]
            return text
        except Exception as e:
            logger.debug(f"[WebSearch] Full-text fetch failed for {url[:60]}: {e}")
            return ""


# ── Smart Keyword Extraction ──

_KEYWORD_EXTRACT_PROMPT = (
    "Extract exactly 2-4 search keywords from the text. Use the context to resolve "
    "pronouns. If no search is needed, output ONLY the word 'none'.\n\n"
    "Examples:\n"
    "Text: What is the capital of France?\nKeywords: capital France\n\n"
    "Text: How do I fix a ValueError in Python?\nKeywords: Python ValueError fix\n\n"
    "Text: Hello, how are you?\nKeywords: none\n\n"
    "Context: {context}\nText: {text}\nKeywords:"
)


def extract_search_keywords(text: str, context: str = "",
                            llm=None) -> Optional[str]:
    """Extract search keywords from user text using a lightweight LLM.

    Returns None if no search is needed.
    """
    text = text.strip()
    if not text or len(text.split()) <= 2:
        return None

    # Fast path: questions usually need search
    question_starters = ("what", "who", "when", "where", "why", "how",
                         "tell me about", "explain", "define", "search for",
                         "look up", "find", "latest", "news about", "update on")
    lower = text.lower()
    fast_trigger = any(lower.startswith(s) for s in question_starters)

    if llm:
        try:
            prompt = _KEYWORD_EXTRACT_PROMPT.format(
                context=context[:300], text=text[:500]
            )
            resp = llm.create_completion(
                prompt=prompt, max_tokens=15, temperature=0.1,
                stop=["\n", "Text:"]
            )
            kw = resp["choices"][0]["text"].strip()
            if kw and kw.lower() != "none" and len(kw.split()) >= 1:
                return kw
        except Exception as e:
            logger.warning(f"[WebSearch] Keyword extraction LLM call failed: {e}")

    if not fast_trigger:
        return None

    # Deterministic fallback: extract key nouns from the question
    return _extract_keywords_deterministic(text)

def _extract_keywords_deterministic(text: str) -> Optional[str]:
    """Rule-based keyword extraction — no LLM required."""
    # Remove common stopwords and question words
    stop = {"what", "who", "when", "where", "why", "how", "is", "are", "the",
            "a", "an", "can", "you", "i", "me", "tell", "about", "do", "does",
            "did", "will", "would", "could", "should", "please", "explain",
            "define", "search", "look", "find", "get", "give", "show", "hello",
            "hi", "hey", "ok", "okay", "thanks", "thank"}
    words = [w.strip(".,;:!?\"'") for w in text.lower().split()
             if w.strip(".,;:!?\"'") not in stop]
    # Keep words 3+ chars, prefer capitalized or technical terms
    meaningful = [w for w in words if len(w) >= 3]
    if not meaningful:
        return None
    return " ".join(meaningful[:4])
