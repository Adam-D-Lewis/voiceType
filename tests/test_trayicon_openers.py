"""Unit tests for trayicon file opener functionality."""

from pathlib import Path
from unittest.mock import patch

import pytest

from voicetype.settings import FileOpenerConfig


class TestOpenFile:
    """Tests for _open_file helper function."""

    def test_open_file_system_default_linux(self, tmp_path):
        """Test opening file with system default on Linux."""
        from voicetype.trayicon import _open_file

        test_file = tmp_path / "test.log"
        test_file.touch()
        config = FileOpenerConfig()  # No command = system default

        with (
            patch("voicetype.trayicon.sys.platform", "linux"),
            patch("subprocess.Popen") as mock_popen,
        ):
            _open_file(test_file, config)
            mock_popen.assert_called_once_with(["xdg-open", str(test_file)])

    def test_open_file_custom_command(self, tmp_path):
        """Test opening file with custom command."""
        from voicetype.trayicon import _open_file

        test_file = tmp_path / "test.log"
        test_file.touch()
        config = FileOpenerConfig(command="code", args=["--goto", "{path}:999999"])

        with patch("subprocess.Popen") as mock_popen:
            _open_file(test_file, config)
            mock_popen.assert_called_once_with(
                ["code", "--goto", f"{test_file}:999999"]
            )

    def test_open_file_custom_command_no_args(self, tmp_path):
        """Test opening file with custom command but no args."""
        from voicetype.trayicon import _open_file

        test_file = tmp_path / "test.log"
        test_file.touch()
        config = FileOpenerConfig(command="code")

        with patch("subprocess.Popen") as mock_popen:
            _open_file(test_file, config)
            mock_popen.assert_called_once_with(["code", str(test_file)])

    def test_open_file_path_substitution(self, tmp_path):
        """Test that {path} is substituted in args."""
        from voicetype.trayicon import _open_file

        test_file = tmp_path / "test.log"
        test_file.touch()
        config = FileOpenerConfig(command="myapp", args=["--file={path}", "--other"])

        with patch("subprocess.Popen") as mock_popen:
            _open_file(test_file, config)
            mock_popen.assert_called_once_with(
                ["myapp", f"--file={test_file}", "--other"]
            )

    def test_open_file_path_in_args_no_append(self, tmp_path):
        """Test that path is not appended when {path} is in args."""
        from voicetype.trayicon import _open_file

        test_file = tmp_path / "test.log"
        test_file.touch()
        config = FileOpenerConfig(command="code", args=["--goto", "{path}:999999"])

        with patch("subprocess.Popen") as mock_popen:
            _open_file(test_file, config)
            # Path should only appear once (substituted), not appended
            call_args = mock_popen.call_args[0][0]
            assert call_args == ["code", "--goto", f"{test_file}:999999"]
