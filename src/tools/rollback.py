import os
import shutil
import logging
from datetime import datetime
from typing import Optional

from src.tools.coding_tools import WORKSPACE_ROOT

logger = logging.getLogger("MultiAgent.Rollback")

BACKUP_ROOT = os.path.join(WORKSPACE_ROOT, ".backups")


def _ensure_backup_dir() -> None:
    """Ensure the backup directory exists."""
    if not os.path.exists(BACKUP_ROOT):
        os.makedirs(BACKUP_ROOT, exist_ok=True)


def backup_file(filepath: str) -> Optional[str]:
    """
    Create a backup of a file before modification.
    Returns the backup path on success, None on failure.
    """
    _ensure_backup_dir()
    
    abs_path = os.path.realpath(os.path.join(WORKSPACE_ROOT, filepath))
    if not os.path.isfile(abs_path):
        return None
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{ts}_{os.path.basename(filepath)}"
    backup_path = os.path.join(BACKUP_ROOT, filepath.replace("/", os.sep), backup_name)
    
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    
    try:
        shutil.copy2(abs_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"Failed to backup {filepath}: {e}")
        return None


def backup_workspace() -> None:
    """
    Creates a snapshot of the entire workspace, excluding .git, .backups, node_modules.
    The snapshot is saved in workspace/.backups/green_snapshot.
    """
    _ensure_backup_dir()
    snapshot_dir = os.path.join(BACKUP_ROOT, "green_snapshot")
    if os.path.exists(snapshot_dir):
        try:
            shutil.rmtree(snapshot_dir)
        except Exception as e:
            logger.warning(f"Could not remove existing snapshot dir {snapshot_dir}: {e}")
            
    ignore_patterns = shutil.ignore_patterns(
        ".git", ".backups", "node_modules", ".pytest_cache", ".code_index_cache.json"
    )
    try:
        shutil.copytree(WORKSPACE_ROOT, snapshot_dir, ignore=ignore_patterns)
        logger.info(f"Workspace snapshot created at {snapshot_dir}")
    except Exception as e:
        logger.error(f"Failed to backup workspace: {e}")


def restore_workspace() -> None:
    """
    Restores the workspace to the stashed green snapshot.
    Deletes any new files/directories that were not in the snapshot,
    and restores modified ones. Keeps .git, .backups, node_modules.
    """
    snapshot_dir = os.path.join(BACKUP_ROOT, "green_snapshot")
    if not os.path.exists(snapshot_dir):
        logger.warning(f"No green snapshot found at {snapshot_dir} to restore.")
        return
        
    logger.info("Restoring workspace from green snapshot...")
    
    # 1. Clean up / delete files and directories in WORKSPACE_ROOT that are not in the snapshot
    exclude_dirs = {".git", ".backups", "node_modules", ".pytest_cache"}
    
    to_delete_files = []
    to_delete_dirs = []
    
    for root, dirs, files in os.walk(WORKSPACE_ROOT, topdown=True):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for f in files:
            abs_path = os.path.join(root, f)
            rel_path = os.path.relpath(abs_path, WORKSPACE_ROOT)
            snapshot_path = os.path.join(snapshot_dir, rel_path)
            if not os.path.exists(snapshot_path):
                to_delete_files.append(abs_path)
        for d in dirs:
            abs_dir_path = os.path.join(root, d)
            rel_dir_path = os.path.relpath(abs_dir_path, WORKSPACE_ROOT)
            snapshot_dir_path = os.path.join(snapshot_dir, rel_dir_path)
            if not os.path.exists(snapshot_dir_path):
                to_delete_dirs.append(abs_dir_path)

    # Delete untracked files
    for f in to_delete_files:
        try:
            os.remove(f)
            logger.info(f"Removed untracked workspace file during rollback: {f}")
        except Exception as e:
            logger.error(f"Failed to remove file {f}: {e}")
            
    # Delete untracked directories (sort them by length descending so subdirs are deleted first)
    to_delete_dirs.sort(key=len, reverse=True)
    for d in to_delete_dirs:
        try:
            if os.path.exists(d):
                shutil.rmtree(d)
                logger.info(f"Removed untracked workspace directory during rollback: {d}")
        except Exception as e:
            logger.error(f"Failed to remove directory {d}: {e}")
                
    # 2. Copy/overwrite files from snapshot back to WORKSPACE_ROOT
    for root, dirs, files in os.walk(snapshot_dir):
        rel_root = os.path.relpath(root, snapshot_dir)
        target_root = WORKSPACE_ROOT if rel_root == "." else os.path.join(WORKSPACE_ROOT, rel_root)
        
        for d in dirs:
            target_dir = os.path.join(target_root, d)
            os.makedirs(target_dir, exist_ok=True)
            
        for f in files:
            source_file = os.path.join(root, f)
            target_file = os.path.join(target_root, f)
            try:
                shutil.copy2(source_file, target_file)
            except Exception as e:
                logger.error(f"Failed to restore file {target_file}: {e}")
                
    logger.info("Workspace restored from green snapshot.")