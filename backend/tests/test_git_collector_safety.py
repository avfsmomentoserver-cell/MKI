"""Regression tests for git collector security fixes (T-N1 symlink containment)."""

import subprocess
import tempfile
from pathlib import Path

import pytest

from mkc.intelligence.ingest.git_collector import GitRepoCollector, _is_safe_path


def test_is_safe_path_rejects_symlinks():
    """T-N1: Symlink containment - reject symlinks even if they point inside repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir()
        
        # Create a regular file (should be safe)
        safe_file = repo_root / "safe.txt"
        safe_file.write_text("safe content")
        assert _is_safe_path(repo_root, safe_file) is True
        
        # Create a symlink pointing inside the repo (should be rejected)
        symlink = repo_root / "symlink.txt"
        symlink.symlink_to(safe_file)
        assert _is_safe_path(repo_root, symlink) is False


def test_is_safe_path_rejects_external_symlinks():
    """T-N1: Symlink containment - reject symlinks pointing outside repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir()
        
        # Create a file outside the repo
        external_file = Path(tmpdir) / "external.txt"
        external_file.write_text("external content")
        
        # Create a symlink pointing outside the repo (should be rejected)
        symlink = repo_root / "symlink.txt"
        symlink.symlink_to(external_file)
        assert _is_safe_path(repo_root, symlink) is False


def test_is_safe_path_rejects_path_traversal():
    """T-N1: Symlink containment - reject paths that resolve outside repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir) / "repo"
        repo_root.mkdir()
        
        # Create a file outside the repo
        external_file = Path(tmpdir) / "external.txt"
        external_file.write_text("external content")
        
        # Test direct external path (should be rejected)
        assert _is_safe_path(repo_root, external_file) is False


def test_git_collector_skips_symlinks():
    """T-N1: Git collector should skip symlinks during collection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test_repo"
        repo_path.mkdir()
        
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True, capture_output=True)
        
        # Create a regular file
        regular_file = repo_path / "regular.txt"
        regular_file.write_text("regular content")
        subprocess.run(["git", "add", "regular.txt"], cwd=repo_path, check=True, capture_output=True)
        
        # Create a symlink pointing to the regular file
        symlink = repo_path / "symlink.txt"
        symlink.symlink_to(regular_file)
        subprocess.run(["git", "add", "symlink.txt"], cwd=repo_path, check=True, capture_output=True)
        
        # Commit both
        subprocess.run(["git", "commit", "-m", "test"], cwd=repo_path, check=True, capture_output=True)
        
        # Collect artifacts
        collector = GitRepoCollector(repo_path)
        artifacts = collector.collect()
        
        # The symlink should be skipped due to safety check
        artifact_paths = [a.path for a in artifacts]
        assert "regular.txt" in artifact_paths
        assert "symlink.txt" not in artifact_paths  # Symlink should be skipped


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
