"""Tool functions used by the ReAct agent."""

import json
import os
import subprocess
from typing import Callable, List

import requests
from duckduckgo_search import DDGS


def create_project_tools(project_dir: str) -> List[Callable]:
    """Create tools that are bound to the specified project directory."""

    def read_file(file_path: str) -> str:
        """Read and return the contents of a file."""
        if not os.path.isabs(file_path):
            file_path = os.path.join(project_dir, file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_to_file(file_path: str, content: str) -> str:
        """Write *content* to *file_path* within the project directory."""
        if not os.path.isabs(file_path):
            file_path = os.path.join(project_dir, file_path)

        dir_path = os.path.dirname(file_path)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content.replace("\\n", "\n"))
        return f"Write successful: {file_path}"

    def run_terminal_command(command: str) -> str:
        """Execute *command* in the project directory and return its output."""
        run_result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=project_dir,
        )

        stdout = (run_result.stdout or "").strip()
        stderr = (run_result.stderr or "").strip()
        exit_code = run_result.returncode

        parts = []
        if stdout:
            parts.append(f"stdout:\n{stdout}")
        if stderr:
            parts.append(f"stderr:\n{stderr}")
        parts.append(f"exit_code={exit_code}")

        result = "\n".join(parts) if parts else f"exit_code={exit_code} (no output)"

        MAX_LEN = 4000
        if len(result) > MAX_LEN:
            result = result[:MAX_LEN] + "\n[truncated]"
        return result

    def web_search(query: str, max_results: int = 5, site: str | None = None) -> str:
        """Search the web via DuckDuckGo and return JSON formatted results."""
        q = query if not site else f"site:{site} {query}"
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(q, max_results=int(max_results)):
                    results.append({
                        "title": r.get("title"),
                        "url": r.get("href"),
                        "snippet": r.get("body"),
                    })
        except Exception as e:
            return f"Search error: {e}"
        return json.dumps(results, ensure_ascii=False, indent=2)

    def fetch_url(url: str, timeout: int = 20) -> str:
        """Fetch *url* and return metadata plus a truncated text preview."""
        headers = {
            "User-Agent": "ReAct-Agent/0.1 (+https://example.com)"
        }
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            ctype = resp.headers.get("content-type", "")
            text_preview = resp.text
            MAX_LEN = 4000
            if len(text_preview) > MAX_LEN:
                text_preview = text_preview[:MAX_LEN] + "\n[truncated]"
            return json.dumps({
                "status_code": resp.status_code,
                "content_type": ctype,
                "text_preview": text_preview,
                "url": resp.url,
            }, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Fetch error: {e}"

    return [read_file, write_to_file, run_terminal_command, web_search, fetch_url]
