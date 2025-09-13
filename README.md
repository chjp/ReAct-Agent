# ReAct Agent

A ReAct (Reasoning + Acting) agent implementation in Python that uses OpenRouter API to interact with language models. The agent follows a structured thinking and action loop to solve problems by breaking them down into steps.

## Setup Instructions

First, make sure you have installed `uv`. If not, please install it following the instructions on:

https://docs.astral.sh/uv/guides/install-python/

Then, create a file called `.env` in the current directory with the following content:

```
OPENROUTER_API_KEY=xxx
```

Replace `xxx` with your actual API Key from OpenRouter. If you don't use OpenRouter, you can modify the code and change the `base_url` to another provider.

## Running the Agent

After ensuring `uv` is installed successfully, navigate to the current directory and execute the following command to start:

```bash
uv run agent.py <project_directory>
```

### Example Usage

```bash
uv run agent.py snakegame
```

This will create a `snakegame` directory and start the agent. You can then enter tasks like:

```
Please write a snake game using HTML, JS, and CSS, with code in separate files
```

### Quick Demo: BWA install

Run the agent in a new project directory `bwainstall`:

```bash
uv run agent.py bwainstall
```

When prompted, paste this task:

```
Please search official document of short read alignment tool bwa and install the latest version
```

## Features

- **ReAct Pattern**: Follows the Reasoning + Acting pattern with structured thinking
- **Tool Integration**: Built-in tools for file operations and terminal commands
- **Project Directory**: Automatically creates and manages project directories
- **Session Logging**: Logs all interactions with timestamps to `.agentrun.log` files
- **Multiple Model Support**: Works with various models through OpenRouter API

## Available Tools

- `read_file(file_path)` - Read file contents
- `write_to_file(file_path, content)` - Write content to files
- `run_terminal_command(command)` - Execute shell commands
- `web_search(query, max_results=5, site=None)` - Search the web (DuckDuckGo). Optionally scope to a specific site.
- `fetch_url(url, timeout=20)` - Fetch a URL and return status, content type, and a truncated text preview.

All file operations use relative paths within the specified project directory.

## References

- ReAct: Synergizing Reasoning and Acting in Language Models — Yao et al., 2022. [arXiv:2210.03629](https://arxiv.org/abs/2210.03629)

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.