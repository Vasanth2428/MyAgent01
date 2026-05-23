import re
import logging
import requests
from urllib.parse import urljoin, urlparse, quote_plus
from typing import List, Dict, Tuple

logger = logging.getLogger("RAG.WebTraversal")

def search_web(query: str) -> List[Dict]:
    """
    Searches DuckDuckGo Lite and returns a list of results.
    Each result contains: title, url, snippet.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url = "https://lite.duckduckgo.com/lite/"
    try:
        logger.info(f"Searching web via DuckDuckGo Lite for: {query}")
        # Use POST to /lite/ as it is more stable and does not get redirected easily
        data = {"q": query}
        response = requests.post(url, headers=headers, data=data, timeout=10)
        if response.status_code != 200:
            logger.warning(f"DuckDuckGo Lite returned status code {response.status_code}")
            return []
        
        html = response.text
        
        # Match class='result-link' anchors
        a_tags = re.findall(r'<a\s+[^>]*class=\s*[\'"]result-link[\'"][^>]*>.*?</a>', html, re.DOTALL)
        snippets = re.findall(r'<td[^>]*class=[\'"]result-snippet[\'"][^>]*>(.*?)</td>', html, re.DOTALL)
        
        results = []
        for idx, a in enumerate(a_tags):
            href_match = re.search(r'href=[\'"]([^\'"]+)[\'"]', a)
            url_val = href_match.group(1) if href_match else ""
            title = re.sub(r'<[^>]+>', '', a).strip()
            
            snippet = snippets[idx].strip() if idx < len(snippets) else ""
            snippet = re.sub(r'<[^>]+>', '', snippet).strip()
            
            # Unescape common HTML entities
            title = title.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'").replace("&lt;", "<").replace("&gt;", ">")
            snippet = snippet.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'").replace("&lt;", "<").replace("&gt;", ">")
            
            # Clean double spaces/newlines
            title = " ".join(title.split())
            snippet = " ".join(snippet.split())
            
            if url_val:
                results.append({
                    "title": title,
                    "url": url_val,
                    "snippet": snippet
                })
        logger.info(f"Found {len(results)} search results.")
        return results
    except Exception as e:
        logger.error(f"Error during DuckDuckGo search: {e}", exc_info=True)
        return []

def fetch_web_page(url: str, max_chars: int = 10000) -> Tuple[str, List[Dict]]:
    """
    Fetches raw HTML, strips script/style/nav/header/footer tags, normalizes whitespace,
    extracts main text content, and returns the top absolute hyperlinks and cleaned text.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        logger.info(f"Fetching web page: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return f"Error: Received status code {response.status_code}", []
        
        # Ensure we read the HTML response
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type and "text/plain" not in content_type:
            return f"Error: Unsupported content type {content_type}", []
            
        html = response.text
        
        # Extract links before stripping tags
        raw_links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.DOTALL | re.IGNORECASE)
        links = []
        seen_urls = set()
        
        for href, text in raw_links:
            href_clean = href.strip()
            # Resolve relative URLs to absolute
            absolute_url = urljoin(url, href_clean)
            
            parsed = urlparse(absolute_url)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                link_text = re.sub(r'<[^>]+>', '', text).strip()
                link_text = " ".join(link_text.split())
                if not link_text:
                    link_text = parsed.netloc # fallback
                
                # Deduplicate links
                if absolute_url not in seen_urls and absolute_url != url:
                    seen_urls.add(absolute_url)
                    links.append({
                        "url": absolute_url,
                        "text": link_text
                    })
        
        # Strip script, style, nav, header, footer, aside tags
        html_clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html_clean = re.sub(r'<style[^>]*>.*?</style>', '', html_clean, flags=re.DOTALL | re.IGNORECASE)
        html_clean = re.sub(r'<header[^>]*>.*?</header>', '', html_clean, flags=re.DOTALL | re.IGNORECASE)
        html_clean = re.sub(r'<footer[^>]*>.*?</footer>', '', html_clean, flags=re.DOTALL | re.IGNORECASE)
        html_clean = re.sub(r'<nav[^>]*>.*?</nav>', '', html_clean, flags=re.DOTALL | re.IGNORECASE)
        html_clean = re.sub(r'<aside[^>]*>.*?</aside>', '', html_clean, flags=re.DOTALL | re.IGNORECASE)
        
        # Extract text content by stripping remaining HTML tags
        text_content = re.sub(r'<[^>]+>', ' ', html_clean)
        # Standardize whitespace
        text_content = " ".join(text_content.split())
        
        # Unescape HTML entities
        text_content = text_content.replace("&amp;", "&").replace("&quot;", '"').replace("&#x27;", "'").replace("&lt;", "<").replace("&gt;", ">")
        
        # Truncate to maximum allowed characters
        truncated_text = text_content[:max_chars]
        if len(text_content) > max_chars:
            truncated_text += " ... [Content Truncated]"
            
        logger.info(f"Successfully fetched {url}. Text length: {len(truncated_text)}, links: {len(links)}")
        return truncated_text, links
    except Exception as e:
        logger.error(f"Error fetching web page {url}: {e}", exc_info=True)
        return f"Error fetching web page: {e}", []
