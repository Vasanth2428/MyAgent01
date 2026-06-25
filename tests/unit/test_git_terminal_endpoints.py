import unittest
from fastapi.testclient import TestClient
from main import app

class TestGitTerminalEndpoints(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_git_status_returns_valid_structure(self):
        response = self.client.get("/git/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("is_repo", data)
        self.assertIn("branch", data)
        self.assertIn("files", data)

    def test_git_init_endpoint(self):
        response = self.client.post("/git/init")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("output", data)

    def test_git_stage_nonexistent_file(self):
        response = self.client.post("/git/stage", json={"file_path": "nonexistent_temp_file.txt", "stage": True})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")

    def test_git_commit_empty_message(self):
        response = self.client.post("/git/commit", json={"message": ""})
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("detail", data)
