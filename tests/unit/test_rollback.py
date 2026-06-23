import os
import shutil
import pytest
from src.tools import rollback

def test_workspace_backup_and_restore(tmp_path, monkeypatch):
    # Set up temp workspace and backup directories
    temp_workspace = tmp_path / "workspace"
    temp_workspace.mkdir()
    
    # Pre-populate some files in the temp workspace
    file_a = temp_workspace / "file_a.txt"
    file_a.write_text("content a")
    
    sub_dir = temp_workspace / "subdir"
    sub_dir.mkdir()
    file_b = sub_dir / "file_b.txt"
    file_b.write_text("content b")
    
    # Excluded directories/files
    node_modules = temp_workspace / "node_modules"
    node_modules.mkdir()
    file_in_node_modules = node_modules / "npm_dep.txt"
    file_in_node_modules.write_text("npm content")
    
    git_dir = temp_workspace / ".git"
    git_dir.mkdir()
    file_in_git = git_dir / "config"
    file_in_git.write_text("git config")
    
    # Monkeypatch WORKSPACE_ROOT and BACKUP_ROOT in rollback module
    monkeypatch.setattr(rollback, "WORKSPACE_ROOT", str(temp_workspace))
    monkeypatch.setattr(rollback, "BACKUP_ROOT", str(temp_workspace / ".backups"))
    
    # 1. Run backup
    rollback.backup_workspace()
    
    # Verify backup exists
    snapshot_dir = temp_workspace / ".backups" / "green_snapshot"
    assert snapshot_dir.exists()
    assert (snapshot_dir / "file_a.txt").exists()
    assert (snapshot_dir / "subdir" / "file_b.txt").exists()
    # Excluded directories must NOT be in backup
    assert not (snapshot_dir / "node_modules").exists()
    assert not (snapshot_dir / ".git").exists()
    
    # 2. Modify, delete and add files in temp workspace
    file_a.write_text("modified content a")
    file_b.unlink()
    
    file_c = temp_workspace / "file_c.txt"
    file_c.write_text("new file c")
    
    # Also add a new untracked directory
    new_sub = temp_workspace / "new_subdir"
    new_sub.mkdir()
    file_d = new_sub / "file_d.txt"
    file_d.write_text("new file d")
    
    # Excluded files are modified or added
    file_in_node_modules.write_text("modified npm content")
    new_git_file = git_dir / "new_git_file"
    new_git_file.write_text("new git file")
    
    # 3. Run restore
    rollback.restore_workspace()
    
    # Verify workspace state
    # Modified file restored
    assert file_a.read_text() == "content a"
    # Deleted file restored
    assert file_b.exists()
    assert file_b.read_text() == "content b"
    # New untracked files and directories deleted
    assert not file_c.exists()
    assert not new_sub.exists()
    # Excluded files kept
    assert file_in_node_modules.read_text() == "modified npm content"
    assert new_git_file.exists()
