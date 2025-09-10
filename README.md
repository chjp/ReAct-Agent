# ReAct Agent

A ReAct (Reasoning + Acting) agent implementation in Python. Instead of calling an API directly, the agent prints the exact JSON payload for each model request. Copy this payload into your preferred web-based LLM, then paste the model's response back into the agent to continue the reasoning loop.

## Setup Instructions

First, make sure you have installed `uv`. If not, please install it following the instructions on:

https://docs.astral.sh/uv/guides/install-python/

No API keys are required; the agent works entirely through manual copy‑and‑paste.

## Running the Agent

After ensuring `uv` is installed successfully, navigate to the current directory and execute the following command to start:

```bash
uv run agent.py <project_directory>
```

### Example Usage

```bash
uv run agent.py snake
```

This will create a `snake` directory and start the agent. When prompted with a JSON request, copy it into a web-based LLM, paste the model's reply back into the terminal, and continue until you reach a final answer.

## Features

- **ReAct Pattern**: Follows the Reasoning + Acting pattern with structured thinking
- **Tool Integration**: Built-in tools for file operations and terminal commands
- **Project Directory**: Automatically creates and manages project directories
- **Session Logging**: Logs all interactions with timestamps to `.agentrun.log` files
- **Manual Model Interaction**: Works with any web-based LLM via copy‑and‑paste

## Available Tools

- `read_file(file_path)` - Read file contents
- `write_to_file(file_path, content)` - Write content to files
- `run_terminal_command(command)` - Execute shell commands

All file operations use relative paths within the specified project directory.