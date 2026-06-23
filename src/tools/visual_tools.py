import os
import logging

logger = logging.getLogger("MultiAgent.VisualTools")

def capture_viewport_screenshot(url: str, output_path: str = "screenshot.png") -> str:
    """
    Captures a screenshot of the page at the given URL and saves it to output_path.
    Returns a success message with the path or an error message.
    """
    from src.tools.coding_tools import _is_safe_path, _get_absolute_path
    
    if not _is_safe_path(output_path):
        return f"Error: Access denied. Output path '{output_path}' violates safety or path policies."
        
    abs_output_path = _get_absolute_path(output_path)
    os.makedirs(os.path.dirname(abs_output_path), exist_ok=True)
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return "Error: Playwright library is not installed. Please install it using 'pip install playwright' and run 'playwright install' to download browser binaries."
        
    try:
        with sync_playwright() as p:
            logger.info(f"Launching headless browser to screenshot: {url}")
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            
            page.goto(url, wait_until="networkidle", timeout=15000)
            page.screenshot(path=abs_output_path)
            browser.close()
            
        return f"Success: Screenshot captured and saved to '{output_path}'."
    except Exception as e:
        logger.error(f"Failed to capture screenshot for {url}: {e}")
        return f"Error capturing screenshot: {e}"
