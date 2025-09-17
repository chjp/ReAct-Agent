"""Entry point for the minimal MCP server."""

from __future__ import annotations

from fastmcp import FastMCP

from . import tools


def create_app() -> FastMCP:
    """Instantiate the MCP server and register available tools."""
    mcp = FastMCP("host info mcp")
    mcp.add_tool(tools.get_host_info)
    return mcp


def main() -> None:
    """Run the server over stdio."""
    create_app().run("stdio")


if __name__ == "__main__":
    main()
