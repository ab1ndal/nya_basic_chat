# Location: src/nya_basic_chat/web.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import os
import requests
from bs4 import BeautifulSoup


@dataclass
class Page:
    url: str
    title: str
    text: str


def fetch_url(url: str, max_chars: int = 12000, timeout: int = 15) -> Page:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "NYA-LightChat/1.0"})
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else url
    text = soup.get_text(separator="\n", strip=True)
    text = "\n".join(line for line in text.splitlines() if line.strip())
    if len(text) > max_chars:
        text = text[:max_chars]
    return Page(url=url, title=title, text=text)


def tavily_search(
    query: str, k: int = 5, api_key: Optional[str] = None, timeout: int = 15
) -> List[Dict[str, Any]]:
    api_key = api_key or os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "max_results": k, "search_depth": "basic"},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json() or {}
    results = data.get("results", []) or []
    out: List[Dict[str, Any]] = []
    for r in results:
        out.append(
            {
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "snippet": (r.get("content") or "")[:400],
            }
        )
    return out
