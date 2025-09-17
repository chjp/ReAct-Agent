import ast
import inspect
import os
import re
from string import Template
from typing import List, Callable, Tuple
import json
from datetime import datetime

import click
from dotenv import load_dotenv
from openai import OpenAI
import platform
import requests
from duckduckgo_search import DDGS

from mcp import tools as mcp_tools

from prompt_template import react_system_prompt_template


def log_and_print(message, log_file=None):
    """Print to console and log to file"""
    print(message)
    if log_file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")


class ReActAgent:
    def __init__(self, tools: List[Callable], model: str, project_directory: str):
        self.tools = { func.__name__: func for func in tools }
        self.model = model
        self.project_directory = project_directory
        
        # Create log file with timestamp under agentlog/ directory next to this file
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(base_dir, "agentlog")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"{timestamp}.agentrun.log")
        
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=ReActAgent.get_api_key(),
        ) # use LiteLLM as alternative

    def run(self, user_input: str):
        messages = [
            {"role": "system", "content": self.render_system_prompt(react_system_prompt_template)},
            {"role": "user", "content": f"<question>{user_input}</question>"}
        ]

        step_count = 0
        MAX_STEPS = 50
        while True:
            step_count += 1
            if step_count > MAX_STEPS:
                return f"Reached maximum step limit ({MAX_STEPS}). Stopping to avoid infinite loop."

            # Request model
            content = self.call_model(messages)

            # Detect Thought
            thought_match = re.search(r"<thought>(.*?)</thought>", content, re.DOTALL)
            if thought_match:
                thought = thought_match.group(1)
                log_and_print(f"\n\n💭 Thought: {thought}", self.log_file)

            # Check if model outputs Final Answer, if so, return directly
            if "<final_answer>" in content:
                final_answer = re.search(r"<final_answer>(.*?)</final_answer>", content, re.DOTALL)
                return final_answer.group(1)

            # Detect Action
            action_match = re.search(r"<action>(.*?)</action>", content, re.DOTALL)
            if not action_match:
                raise RuntimeError("Model did not output <action>")
            action = action_match.group(1)
            tool_name, args = self.parse_action(action)

            log_and_print(f"\n\n🔧 Action: {tool_name}({', '.join(args)})", self.log_file)
            # Only terminal commands need user confirmation, other tools execute directly
            should_continue = input(f"\n\nContinue? (Y/N): ") if tool_name == "run_terminal_command" else "y"
            if should_continue.lower() != 'y':
                log_and_print("\n\nOperation cancelled.", self.log_file)
                return "Operation cancelled by user"

            try:
                observation = self.tools[tool_name](*args)
            except Exception as e:
                observation = f"Tool execution error: {str(e)}"
            log_and_print(f"\n\n🔍 Observation：{observation}", self.log_file)
            obs_msg = f"<observation>{observation}</observation>"
            messages.append({"role": "user", "content": obs_msg})


    def get_tool_list(self) -> str:
        """Generate tool list string with function signatures and descriptions"""
        tool_descriptions = []
        for func in self.tools.values():
            name = func.__name__
            signature = str(inspect.signature(func))
            doc = inspect.getdoc(func)
            tool_descriptions.append(f"- {name}{signature}: {doc}")
        return "\n".join(tool_descriptions)

    def render_system_prompt(self, system_prompt_template: str) -> str:
        """Render system prompt template, replace variables"""
        tool_list = self.get_tool_list()
        try:
            entries = sorted(os.listdir(self.project_directory))
        except Exception:
            entries = []
        MAX_FILES_IN_PROMPT = 50
        overflow = max(0, len(entries) - MAX_FILES_IN_PROMPT)
        shown = entries[:MAX_FILES_IN_PROMPT]
        file_list = ", ".join(shown) + (f" (+{overflow} more)" if overflow else "")
        return Template(system_prompt_template).substitute(
            operating_system=self.get_operating_system_name(),
            tool_list=tool_list,
            file_list=file_list
        )

    @staticmethod
    def get_api_key() -> str:
        """Load the API key from an environment variable."""
        load_dotenv()
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable not found. Please set it in .env file.")
        return api_key

    def call_model(self, messages):
        log_and_print("\n\nRequesting model, please wait...", self.log_file)
        
        # Log the exact JSON payload sent to OpenRouter API
        request_payload = {
            "model": self.model,
            "messages": messages
        }
        
        log_and_print(f"\n" + "="*80, self.log_file)
        log_and_print(f"📋 EXACT JSON REQUEST (copy-paste to GPT-O or API testing)", self.log_file)
        log_and_print(f"="*80, self.log_file)
        log_and_print(json.dumps(request_payload, indent=2, ensure_ascii=False), self.log_file)
        log_and_print(f"="*80 + "\n", self.log_file)
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        content = response.choices[0].message.content
        
        # Log the response from model
        log_and_print(f"\n📥 MODEL RESPONSE:\n{content}", self.log_file)
        
        messages.append({"role": "assistant", "content": content})
        return content

    def parse_action(self, code_str: str) -> Tuple[str, List[str]]:
        match = re.match(r'(\w+)\((.*)\)', code_str, re.DOTALL)
        if not match:
            raise ValueError("Invalid function call syntax")

        func_name = match.group(1)
        args_str = match.group(2).strip()

        # Manually parse parameters, especially handle strings containing multi-line content
        args = []
        current_arg = ""
        in_string = False
        string_char = None
        i = 0
        paren_depth = 0
        
        while i < len(args_str):
            char = args_str[i]
            
            if not in_string:
                if char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    current_arg += char
                elif char == '(':
                    paren_depth += 1
                    current_arg += char
                elif char == ')':
                    paren_depth -= 1
                    current_arg += char
                elif char == ',' and paren_depth == 0:
                    # Encountered top-level comma, end current parameter
                    args.append(self._parse_single_arg(current_arg.strip()))
                    current_arg = ""
                else:
                    current_arg += char
            else:
                current_arg += char
                if char == string_char and (i == 0 or args_str[i-1] != '\\'):
                    in_string = False
                    string_char = None
            
            i += 1
        
        # Add the last parameter
        if current_arg.strip():
            args.append(self._parse_single_arg(current_arg.strip()))
        
        return func_name, args
    
    def _parse_single_arg(self, arg_str: str):
        """Parse single parameter using Python literal semantics when possible."""
        arg_str = arg_str.strip()

        # Prefer ast.literal_eval for quoted strings and Python literals
        try:
            return ast.literal_eval(arg_str)
        except (SyntaxError, ValueError):
            # Fall back to raw string when not a valid literal
            # Strip matching quotes if present without interpreting escapes
            if (arg_str.startswith('"') and arg_str.endswith('"')) or \
               (arg_str.startswith("'") and arg_str.endswith("'")):
                return arg_str[1:-1]
            return arg_str

    def get_operating_system_name(self):
        os_map = {
            "Darwin": "macOS",
            "Windows": "Windows",
            "Linux": "Linux"
        }

        return os_map.get(platform.system(), "Unknown")


def create_project_tools(project_dir):
    """Create tools that are bound to the project directory"""
    
    def read_file(file_path):
        """Used to read file contents"""
        # If relative path, make it relative to project directory
        if not os.path.isabs(file_path):
            file_path = os.path.join(project_dir, file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_to_file(file_path, content):
        """Write specified content to specified file"""
        # If relative path, make it relative to project directory
        if not os.path.isabs(file_path):
            file_path = os.path.join(project_dir, file_path)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content.replace("\\n", "\n"))
        return f"Write successful: {file_path}"

    def run_terminal_command(command):
        """Used to execute terminal commands"""
        import subprocess
        # Run command in the project directory and return stdout/stderr with exit code
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

        # Truncate overly long outputs to keep observations manageable
        MAX_LEN = 4000
        if len(result) > MAX_LEN:
            result = result[:MAX_LEN] + "\n[truncated]"
        return result
    
    def web_search(query, max_results=5, site=None):
        """Search the web (DuckDuckGo). Optionally limit to a specific site via site=example.com.
        Returns up to max_results results with title, url, and snippet."""
        q = query if not site else f"site:{site} {query}"
        results = []
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(q, max_results=int(max_results)):
                    # r typically has {title, href, body}
                    results.append({
                        "title": r.get("title"),
                        "url": r.get("href"),
                        "snippet": r.get("body"),
                    })
        except Exception as e:
            return f"Search error: {e}"
        return json.dumps(results, ensure_ascii=False, indent=2)

    def fetch_url(url, timeout=20):
        """Fetch a URL and return status code, content-type, and a text preview.
        For binary or very large responses, returns a truncated preview."""
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

    def host_info() -> str:
        """Return host information via the MCP tool implementation."""
        return mcp_tools.get_host_info()
    
    return [read_file, write_to_file, run_terminal_command, web_search, fetch_url, host_info]

@click.command()
@click.argument('project_directory',
                type=click.Path(file_okay=False, dir_okay=True))
def main(project_directory):
    project_dir = os.path.abspath(project_directory)
    
    # Create directory if it doesn't exist
    if not os.path.exists(project_dir):
        os.makedirs(project_dir)
        log_and_print(f"Created directory: {project_dir}", None)

    tools = create_project_tools(project_dir)
    #agent = ReActAgent(tools=tools, model="meta-llama/llama-3.2-3b-instruct:free", project_directory=project_dir)
    agent = ReActAgent(tools=tools, model="deepseek/deepseek-chat-v3.1", project_directory=project_dir)

    task = input("Please enter task: ")

    final_answer = agent.run(task)

    log_and_print(f"\n\n✅ Final Answer：{final_answer}", agent.log_file)

if __name__ == "__main__":
    main()
