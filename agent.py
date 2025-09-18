import ast
import inspect
import os
import re
from string import Template
from typing import List, Callable, Tuple, Optional
import json
from datetime import datetime

import click
from dotenv import load_dotenv
from openai import OpenAI
import platform
import pyperclip
from pyperclip import PyperclipException

from tools import create_project_tools

from prompt_template import react_system_prompt_template


def log_and_print(message, log_file=None):
    """Print to console and log to file"""
    print(message)
    if log_file:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")


class ReActAgent:
    def __init__(
        self,
        tools: List[Callable],
        model: str,
        project_directory: str,
        manual_mode: bool = False,
    ):
        self.tools = { func.__name__: func for func in tools }
        self.model = model
        self.project_directory = project_directory
        self.manual_mode = manual_mode

        # Create log file with timestamp under agentlog/ directory next to this file
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        base_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(base_dir, "agentlog")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, f"{timestamp}.agentrun.log")

        self.client: Optional[OpenAI] = None
        if not self.manual_mode:
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

    def copy_payload_to_clipboard(self, payload_text: str) -> None:
        """Copy payload text to clipboard, warn if not available."""
        try:
            pyperclip.copy(payload_text)
            log_and_print("📎 JSON payload copied to clipboard.", self.log_file)
        except PyperclipException as exc:
            log_and_print("⚠️ Unable to copy payload to clipboard automatically.", self.log_file)
            log_and_print(f"Reason: {exc}", self.log_file)
            log_and_print("Please copy the payload manually from the log above.", self.log_file)

    def collect_manual_response(self) -> str:
        """Prompt the user to paste a manual model response."""
        instructions = (
            "Manual mode is enabled. Paste the model's response now.\n"
            "When finished, enter a line containing only END and press Enter."
        )
        while True:
            log_and_print(instructions, self.log_file)
            lines = []
            while True:
                try:
                    line = input()
                except EOFError:
                    raise RuntimeError("Unexpected EOF while reading manual response.")
                if line.strip() == "END":
                    break
                lines.append(line)
            content = "\n".join(lines).strip()
            if content:
                return content
            log_and_print("Manual response was empty. Please try again.", self.log_file)

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
        payload_text = json.dumps(request_payload, indent=2, ensure_ascii=False)
        log_and_print(payload_text, self.log_file)
        log_and_print(f"="*80 + "\n", self.log_file)

        if self.manual_mode:
            self.copy_payload_to_clipboard(payload_text)
            content = self.collect_manual_response()
        else:
            if self.client is None:
                raise RuntimeError("OpenAI client not initialized.")
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


@click.command()
@click.option(
    "--manual",
    is_flag=True,
    help="Copy requests to clipboard and paste model responses manually.",
)
@click.argument('project_directory',
                type=click.Path(file_okay=False, dir_okay=True))
def main(manual, project_directory):
    project_dir = os.path.abspath(project_directory)

    # Create directory if it doesn't exist
    if not os.path.exists(project_dir):
        os.makedirs(project_dir)
        log_and_print(f"Created directory: {project_dir}", None)

    tools = create_project_tools(project_dir)
    #agent = ReActAgent(tools=tools, model="meta-llama/llama-3.2-3b-instruct:free", project_directory=project_dir)
    agent = ReActAgent(
        tools=tools,
        model="deepseek/deepseek-chat-v3.1",
        project_directory=project_dir,
        manual_mode=manual,
    )

    task = input("Please enter task: ")

    final_answer = agent.run(task)

    log_and_print(f"\n\n✅ Final Answer：{final_answer}", agent.log_file)

if __name__ == "__main__":
    main()
