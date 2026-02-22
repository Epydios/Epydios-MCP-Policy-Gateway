from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import subprocess
import time
import os


class SandboxError(RuntimeError):
    pass


def _safe_join(root: Path, rel: str) -> Path:
    # Resolve safely within root. Disallow absolute paths and path escapes.
    root_resolved = root.resolve()
    p = Path(rel)
    if p.is_absolute():
        raise SandboxError("Absolute paths are not allowed.")
    candidate = (root_resolved / p).resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        raise SandboxError("Path escape detected.")
    return candidate


@dataclass
class SandboxExecutor:
    sandbox_dir: Path
    # Allowed command name -> absolute path
    command_paths: Dict[str, str]
    timeout_seconds: float = 5.0
    max_stdout_chars: int = 20000
    max_stderr_chars: int = 20000

    # Resource limits (best effort; POSIX only)
    rlimit_cpu_seconds: int = 2
    rlimit_fsize_bytes: int = 1_000_000
    rlimit_as_bytes: int = 512_000_000
    rlimit_nproc: int = 64
    rlimit_nofile: int = 128

    def __post_init__(self):
        self.sandbox_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.sandbox_dir, 0o700)
        except Exception:
            pass

    def fs_list(self, path: str = ".") -> Dict[str, Any]:
        p = _safe_join(self.sandbox_dir, path)
        if not p.exists():
            raise SandboxError("Path does not exist.")
        if not p.is_dir():
            raise SandboxError("Path is not a directory.")
        items = []
        for child in sorted(p.iterdir(), key=lambda x: x.name):
            items.append({
                "name": child.name,
                "is_dir": child.is_dir(),
                "size": child.stat().st_size if child.is_file() else None,
            })
        return {"path": str(p.relative_to(self.sandbox_dir.resolve())), "items": items}

    def fs_read(self, path: str) -> Dict[str, Any]:
        p = _safe_join(self.sandbox_dir, path)
        if not p.exists() or not p.is_file():
            raise SandboxError("File does not exist.")
        data = p.read_text(encoding="utf-8", errors="replace")
        if len(data) > 100_000:
            data = data[:100_000] + "\n...[truncated]..."
        return {"path": str(p.relative_to(self.sandbox_dir.resolve())), "content": data}

    def fs_write(self, path: str, content: str, mode: str = "overwrite") -> Dict[str, Any]:
        if content is None:
            content = ""
        if len(content) > 200_000:
            raise SandboxError("Write too large for prototype sandbox (max 200k chars).")
        p = _safe_join(self.sandbox_dir, path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if mode not in ("overwrite", "append"):
            raise SandboxError("Invalid mode. Use overwrite|append.")
        if mode == "append":
            with p.open("a", encoding="utf-8") as f:
                f.write(content)
        else:
            p.write_text(content, encoding="utf-8")
        return {"path": str(p.relative_to(self.sandbox_dir.resolve())), "bytes_written": len(content), "mode": mode}

    def shell_exec(self, argv: List[str]) -> Dict[str, Any]:
        if not argv or not isinstance(argv, list):
            raise SandboxError("argv must be a non-empty list.")
        cmd = str(argv[0])

        # Disallow suspicious args broadly (prototype-safe defaults).
        for a in argv[1:]:
            if not isinstance(a, str):
                raise SandboxError("argv must contain only strings.")
            if a.startswith("/") or a.startswith("~") or ".." in a:
                raise SandboxError("Absolute paths, '~', and '..' are not allowed in argv.")
            if "\x00" in a:
                raise SandboxError("NUL byte not allowed in argv.")

        abs_cmd = self.command_paths.get(cmd)
        if not abs_cmd:
            raise SandboxError(f"Command not allowed or not resolved: {cmd}")

        # Minimal environment: avoid inheriting potentially dangerous variables.
        env = {"LANG": "C", "LC_ALL": "C"}

        preexec = None
        if os.name == "posix":
            try:
                import resource

                def _limit():
                    # CPU time
                    resource.setrlimit(resource.RLIMIT_CPU, (self.rlimit_cpu_seconds, self.rlimit_cpu_seconds))
                    # Max file size
                    resource.setrlimit(resource.RLIMIT_FSIZE, (self.rlimit_fsize_bytes, self.rlimit_fsize_bytes))
                    # Address space
                    resource.setrlimit(resource.RLIMIT_AS, (self.rlimit_as_bytes, self.rlimit_as_bytes))
                    # Processes and open files (best effort)
                    try:
                        resource.setrlimit(resource.RLIMIT_NPROC, (self.rlimit_nproc, self.rlimit_nproc))
                    except Exception:
                        pass
                    try:
                        resource.setrlimit(resource.RLIMIT_NOFILE, (self.rlimit_nofile, self.rlimit_nofile))
                    except Exception:
                        pass

                preexec = _limit
            except Exception:
                preexec = None

        start = time.time()
        proc = subprocess.run(
            [abs_cmd, *argv[1:]],
            cwd=str(self.sandbox_dir),
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
            check=False,
            shell=False,
            env=env,
            preexec_fn=preexec,
            start_new_session=True,
        )
        dur = time.time() - start
        stdout = proc.stdout[-self.max_stdout_chars:]
        stderr = proc.stderr[-self.max_stderr_chars:]
        return {
            "argv": [cmd, *argv[1:]],
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "duration_seconds": dur,
        }
