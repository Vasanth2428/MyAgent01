import pytest
from src.tools.patch_tools import apply_patch

def test_apply_patch_basic():
    original = "line 1\nline 2\nline 3\n"
    patch = """--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
 line 1
-line 2
+line 2 modified
 line 3
"""
    result = apply_patch(original, patch)
    assert result == "line 1\nline 2 modified\nline 3\n"

def test_apply_patch_whitespace_tolerant():
    original = "line 1  with   spaces\nline 2\nline 3\n"
    patch = """--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,3 @@
 line 1 with spaces
-line 2
+line 2 modified
 line 3
"""
    result = apply_patch(original, patch)
    assert result == "line 1  with   spaces\nline 2 modified\nline 3\n"

def test_apply_patch_indentation_shift():
    original = "    def func():\n        return 1\n"
    patch = """--- a/file.txt
+++ b/file.txt
@@ -1,2 +1,3 @@
  def func():
+     logger.info("called")
      return 1
"""
    result = apply_patch(original, patch)
    expected = "    def func():\n        logger.info(\"called\")\n        return 1\n"
    assert result == expected
