"""MCP tool registration entry point."""

from backend.mcp.tool_registry import ToolRegistry


def init_mcp_tools() -> ToolRegistry:
    ToolRegistry.clear()

    from backend.mcp.tools import code_tools, column_tools, name_tools, orm_tools, survey_tools

    survey_tools.register_all(ToolRegistry)
    column_tools.register_all(ToolRegistry)
    name_tools.register_all(ToolRegistry)
    code_tools.register_all(ToolRegistry)
    orm_tools.register_all(ToolRegistry)
    return ToolRegistry

