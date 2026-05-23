import unittest
from unittest.mock import patch, MagicMock
from core.web_traversal import search_web, fetch_web_page

class TestWebTraversal(unittest.TestCase):

    @patch("requests.post")
    def test_search_web_success(self, mock_post):
        # Mock successful DuckDuckGo Lite response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = """
        <html>
        <body>
            <table>
                <tr>
                    <td>
                        <a class="result-link" href="https://example.com/item1">Example Title One</a>
                    </td>
                </tr>
                <tr>
                    <td class="result-snippet">This is the first example snippet containing info.</td>
                </tr>
                <tr>
                    <td>
                        <a class="result-link" href="https://example.com/item2">Example Title Two</a>
                    </td>
                </tr>
                <tr>
                    <td class="result-snippet">This is the second example snippet.</td>
                </tr>
            </table>
        </body>
        </html>
        """
        mock_post.return_value = mock_response

        results = search_web("test query")
        
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "Example Title One")
        self.assertEqual(results[0]["url"], "https://example.com/item1")
        self.assertEqual(results[0]["snippet"], "This is the first example snippet containing info.")
        self.assertEqual(results[1]["title"], "Example Title Two")
        self.assertEqual(results[1]["url"], "https://example.com/item2")
        self.assertEqual(results[1]["snippet"], "This is the second example snippet.")

    @patch("requests.post")
    def test_search_web_failure_status(self, mock_post):
        # Mock failure response status code
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        results = search_web("test query")
        self.assertEqual(results, [])

    @patch("requests.post")
    def test_search_web_exception(self, mock_post):
        # Mock network exception
        mock_post.side_effect = Exception("Connection Refused")
        results = search_web("test query")
        self.assertEqual(results, [])

    @patch("requests.get")
    def test_fetch_web_page_success(self, mock_get):
        # Mock successful fetch response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = """
        <html>
            <head>
                <style>body { color: red; }</style>
                <script>console.log('hello');</script>
            </head>
            <body>
                <header>Navigation and Logo Here</header>
                <nav><a href="/home">Home</a></nav>
                <main>
                    <h1>Page Headline</h1>
                    <p>This is the main web page text content that is highly relevant to user research.</p>
                    <a href="https://other.com/target">Outbound Link</a>
                    <a href="/relative/path">Relative Link</a>
                </main>
                <aside>Related sidebar information.</aside>
                <footer>Copyright 2026</footer>
            </body>
        </html>
        """
        mock_get.return_value = mock_response

        text, links = fetch_web_page("https://example.com/start")
        
        # Verify style, head, header, nav, aside, footer are stripped.
        # Main text content is preserved.
        self.assertIn("Page Headline", text)
        self.assertIn("This is the main web page text content", text)
        self.assertNotIn("Navigation and Logo", text)
        self.assertNotIn("body { color: red; }", text)
        self.assertNotIn("console.log", text)
        self.assertNotIn("Copyright 2026", text)

        # Verify links were parsed and resolved correctly
        self.assertEqual(len(links), 3)
        self.assertEqual(links[0]["url"], "https://example.com/home")
        self.assertEqual(links[0]["text"], "Home")
        self.assertEqual(links[1]["url"], "https://other.com/target")
        self.assertEqual(links[1]["text"], "Outbound Link")
        self.assertEqual(links[2]["url"], "https://example.com/relative/path")
        self.assertEqual(links[2]["text"], "Relative Link")

    @patch("requests.get")
    def test_fetch_web_page_unsupported_mime(self, mock_get):
        # Mock unsupported content type
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/pdf"}
        mock_get.return_value = mock_response

        text, links = fetch_web_page("https://example.com/doc.pdf")
        self.assertTrue(text.startswith("Error"))
        self.assertEqual(links, [])

    @patch("requests.get")
    def test_fetch_web_page_status_failure(self, mock_get):
        # Mock HTTP status failure
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        text, links = fetch_web_page("https://example.com/missing")
        self.assertTrue(text.startswith("Error: Received status code 404"))
        self.assertEqual(links, [])

if __name__ == "__main__":
    unittest.main()
