from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from aimxs_gateway.executor.sandbox import SandboxError, SandboxExecutor


class TestSandboxExecutorSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.exec = SandboxExecutor(
            sandbox_dir=self.root,
            command_paths={"echo": shutil.which("echo") or "/bin/echo"},
            timeout_seconds=2.0,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_fs_write_read_list(self):
        out = self.exec.fs_write("notes/hello.txt", "hello")
        self.assertEqual(out["bytes_written"], 5)
        listed = self.exec.fs_list("notes")
        self.assertEqual(len(listed["items"]), 1)
        read = self.exec.fs_read("notes/hello.txt")
        self.assertEqual(read["content"], "hello")

    def test_path_escape_blocked(self):
        with self.assertRaises(SandboxError):
            self.exec.fs_read("../outside.txt")

    def test_shell_exec_echo(self):
        path = self.exec.command_paths.get("echo")
        if not path or not Path(path).exists():
            self.skipTest("echo executable not available")
        out = self.exec.shell_exec(["echo", "hello"])
        self.assertEqual(out["returncode"], 0)
        self.assertIn("hello", out["stdout"])


if __name__ == "__main__":
    unittest.main()
