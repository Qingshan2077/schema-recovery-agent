"""MCP tool registration entry point."""

from backend.mcp.tool_registry import ToolRegistry
from backend.agent.runtime.tool_runtime import ToolRuntime


def init_mcp_tools(tool_runtime: ToolRuntime | None = None) -> ToolRegistry:
    registry = ToolRegistry(runtime=tool_runtime)

    from backend.mcp.tools import catalog_tools, code_tools, column_tools, dba_tools, name_tools, orm_tools, qa_tools, survey_tools

    survey_tools.register_all(registry)
    column_tools.register_all(registry)
    name_tools.register_all(registry)
    code_tools.register_all(registry)
    orm_tools.register_all(registry)
    qa_tools.register_all(registry)
    catalog_tools.register_all(registry)
    dba_tools.register_all(registry)
    return registry
