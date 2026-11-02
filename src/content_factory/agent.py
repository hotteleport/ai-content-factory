"""Run Claude Code as a restricted, non-interactive writing agent.

The agent gets research tools only. It has no shell or file access and never
sees credentials: it returns text, and the engine decides what to do with it.
Ideas and web pages are untrusted input, so this boundary limits the damage a
prompt injection can do.
"""

import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Optional

from .tasks import IDEA, Task

RESEARCH_TOOLS = "WebSearch,WebFetch"


@dataclass(frozen=True)
class AgentResult:
    ok: bool
    text: str = ""
    error: str = ""


def _untrusted(value: Optional[str]) -> str:
    # Stops input from closing the delimiters that mark it as data.
    return (value or "").replace("<", "&lt;").replace(">", "&gt;")


class PromptLibrary:
    """Loads prompts from a private directory that is kept out of the repository."""

    def __init__(self, directory: Path):
        directory = Path(directory)
        self.system = (directory / "system.md").read_text(encoding="utf-8")
        self._draft = Template((directory / "draft.md").read_text(encoding="utf-8"))
        self._revise = Template((directory / "revise.md").read_text(encoding="utf-8"))

    def render(self, task: Task) -> str:
        if task.kind == IDEA:
            return self._draft.substitute(idea=_untrusted(task.text))
        return self._revise.substitute(
            original=_untrusted(task.original),
            quote=_untrusted(task.quote),
            request=_untrusted(task.text),
        )


def build_command(system_prompt: str, model: Optional[str] = None) -> list:
    command = [
        "claude",
        "--print",
        "--output-format", "text",
        "--tools", RESEARCH_TOOLS,
        "--allowedTools", RESEARCH_TOOLS,
        "--strict-mcp-config",
        "--no-session-persistence",
        "--append-system-prompt", system_prompt,
    ]
    if model:
        command += ["--model", model]
    return command


class AgentRun:
    """A running agent process, polled so the engine can keep watching Telegram."""

    def __init__(self, command: list, prompt: str, timeout_seconds: int, workdir: Path):
        self._stdin = tempfile.TemporaryFile("w+", encoding="utf-8")
        self._stdin.write(prompt)
        self._stdin.seek(0)
        # Temporary files instead of pipes: a full pipe buffer would block the agent.
        self._stdout = tempfile.TemporaryFile("w+", encoding="utf-8")
        self._stderr = tempfile.TemporaryFile("w+", encoding="utf-8")
        self._deadline = time.monotonic() + timeout_seconds
        self._process = subprocess.Popen(
            command, stdin=self._stdin, stdout=self._stdout, stderr=self._stderr, cwd=workdir
        )

    def poll(self) -> Optional[AgentResult]:
        """Return the result once the process has ended, otherwise None."""
        code = self._process.poll()
        if code is None:
            if time.monotonic() < self._deadline:
                return None
            self._process.kill()
            self._process.wait()
            self._close()
            return AgentResult(False, error="agent timed out")

        self._stdout.seek(0)
        self._stderr.seek(0)
        text = self._stdout.read().strip()
        error = self._stderr.read().strip()
        self._close()
        if code != 0:
            return AgentResult(False, error=error[-500:] or f"agent exited with code {code}")
        if not text:
            return AgentResult(False, error="agent returned no text")
        return AgentResult(True, text=text)

    def _close(self) -> None:
        for handle in (self._stdin, self._stdout, self._stderr):
            handle.close()


class ClaudeAgent:
    def __init__(self, prompts: PromptLibrary, workdir: Path, timeout_seconds: int, model: Optional[str] = None):
        self._prompts = prompts
        self._workdir = workdir
        self._timeout = timeout_seconds
        self._model = model

    def start(self, task: Task) -> AgentRun:
        command = build_command(self._prompts.system, self._model)
        return AgentRun(command, self._prompts.render(task), self._timeout, self._workdir)
