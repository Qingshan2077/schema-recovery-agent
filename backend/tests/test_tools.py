from backend.mcp.server import init_mcp_tools


def test_tools_register():
    registry = init_mcp_tools()
    tools = registry.list_tools()
    tool_names = [tool["name"] for tool in tools]
    assert len(tools) >= 15
    assert "connect_database" in tool_names
    assert "list_tables" in tool_names
    assert "analyze_table_columns" in tool_names
    assert "find_column_name_matches" in tool_names
    assert "parse_view_definition" in tool_names


def test_connect_database():
    registry = init_mcp_tools()
    result = registry.execute("connect_database")
    assert result["connected"] is True


def test_list_tables():
    registry = init_mcp_tools()
    result = registry.execute("list_tables")
    assert result["table_count"] == 30

