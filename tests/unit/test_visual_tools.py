import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from src.tools.visual_tools import capture_viewport_screenshot
from src.tools.coding_tools import WORKSPACE_ROOT


def test_capture_viewport_screenshot_missing_playwright():
    result = capture_viewport_screenshot("https://example.com", "screenshot.png")
    assert "not installed" in result.lower() or "playwright" in result.lower()


def test_capture_viewport_screenshot_unsafe_path():
    result = capture_viewport_screenshot("https://example.com", "/etc/passwd")
    assert "Access denied" in result or "violates safety" in result


def test_capture_viewport_screenshot_happy_path():
    mock_playwright_module = MagicMock()
    mock_playwright_sync_api = MagicMock()
    mock_playwright_module.sync_api = mock_playwright_sync_api
    mock_sync_playwright = MagicMock()
    mock_playwright_sync_api.sync_playwright = mock_sync_playwright

    mock_playwright_instance = MagicMock()
    mock_browser = MagicMock()
    mock_page = MagicMock()

    mock_context_manager = MagicMock()
    mock_context_manager.__enter__ = MagicMock(return_value=mock_playwright_instance)
    mock_context_manager.__exit__ = MagicMock(return_value=False)

    mock_sync_playwright.return_value = mock_context_manager
    mock_playwright_instance.chromium.launch.return_value = mock_browser
    mock_browser.new_page.return_value = mock_page

    with patch.dict(sys.modules, {
        "playwright": mock_playwright_module,
        "playwright.sync_api": mock_playwright_sync_api,
    }):
        rel_path = "screenshot.png"
        safe_path = os.path.join(WORKSPACE_ROOT, rel_path)

        result = capture_viewport_screenshot("https://example.com", rel_path)

        assert "Success" in result
        assert rel_path in result
        mock_browser.new_page.assert_called_once()
        mock_page.goto.assert_called_once_with("https://example.com", wait_until="networkidle", timeout=15000)
        mock_page.screenshot.assert_called_once_with(path=safe_path)
        mock_browser.close.assert_called_once()
