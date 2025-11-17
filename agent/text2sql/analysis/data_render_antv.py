import os
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from agent.text2sql.state.agent_state import AgentState
from agent.text2sql.analysis.data_render_apache import extract_table_names_sqlglot, get_column_comments
from services.db_qadata_process import process

"""
AntV mcp 数据渲染节点
"""


async def data_render_ant(state: AgentState):
    """蚂蚁 AntV 数据图表渲染，支持无 MCP-Hub 的 STDIO 模式；当MCP不可用时回退为Apache ECharts渲染"""
    server_configs = {}
    if os.getenv("MCP_HUB_DATABASE_QA_GROUP_URL"):
        server_configs["mcphub-sse"] = {
            "url": os.getenv("MCP_HUB_DATABASE_QA_GROUP_URL"),
            "transport": "sse",
        }
    server_configs["mcp-server-chart"] = {
        "command": "npx",
        "args": ["-y", "@antv/mcp-server-chart"],
        "transport": "stdio",
    }
    client = MultiServerMCPClient(server_configs)

    # 获取上一个步骤目标工具 过滤工具集减少token和大模型幻觉问题
    chart_type = state["chart_type"]
    requested_tool = chart_type.replace("mcp-server-chart-", "")
    try:
        tools = await client.get_tools()
        tools = [tool for tool in tools if tool.name in [chart_type, requested_tool]]
    except Exception:
        try:
            fallback_client = MultiServerMCPClient(
                {
                    "mcp-server-chart": {
                        "command": "npx",
                        "args": ["-y", "@antv/mcp-server-chart"],
                        "transport": "stdio",
                    }
                }
            )
            tools = await fallback_client.get_tools()
            tools = [tool for tool in tools if tool.name in [chart_type, requested_tool]]
        except Exception:
            # 构建Apache ECharts回退数据
            generated_sql = state.get("generated_sql", "")
            data_result = state.get("execution_result")
            db_info = state.get("db_info", {})
            # 提取目标表及列中文名
            target_tables = extract_table_names_sqlglot(generated_sql)
            target_table = target_tables[0] if target_tables else ""
            column_comments = get_column_comments(db_info, target_table)
            # 兼容英文字段名提取
            try:
                columns = db_info.get(target_table, {}).get("columns", {})
                if not columns:
                    columns = db_info.get("columns", {})
                english_columns = list(columns.keys())
            except Exception:
                english_columns = []

            table_data = {"llm": {"type": _map_chart_type(chart_type), "sql": generated_sql}, "data": {"column": column_comments, "result": []}}
            if data_result and getattr(data_result, "data", None):
                for row in data_result.data:
                    if isinstance(row, dict):
                        row_values = [row.get(col, None) for col in english_columns]
                        table_data["data"]["result"].append(dict(zip(column_comments, row_values)))

            processed_data = process(json.dumps(table_data, ensure_ascii=False))
            state["apache_chart_data"] = processed_data
            state["chart_url"] = ""
            return state

    # 当没有匹配的工具时触发回退
    if not tools:
        generated_sql = state.get("generated_sql", "")
        data_result = state.get("execution_result")
        db_info = state.get("db_info", {})
        target_tables = extract_table_names_sqlglot(generated_sql)
        target_table = target_tables[0] if target_tables else ""
        column_comments = get_column_comments(db_info, target_table)
        try:
            columns = db_info.get(target_table, {}).get("columns", {})
            if not columns:
                columns = db_info.get("columns", {})
            english_columns = list(columns.keys())
        except Exception:
            english_columns = []

        table_data = {"llm": {"type": _map_chart_type(chart_type), "sql": generated_sql}, "data": {"column": column_comments, "result": []}}
        if data_result and getattr(data_result, "data", None):
            for row in data_result.data:
                if isinstance(row, dict):
                    row_values = [row.get(col, None) for col in english_columns]
                    table_data["data"]["result"].append(dict(zip(column_comments, row_values)))

        processed_data = process(json.dumps(table_data, ensure_ascii=False))
        state["apache_chart_data"] = processed_data
        state["chart_url"] = ""
        return state

    llm = ChatOpenAI(
        model=os.getenv("MODEL_NAME", "qwen-plus"),
        temperature=float(os.getenv("MODEL_TEMPERATURE", 0.75)),
        base_url=os.getenv("MODEL_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        api_key=os.getenv("MODEL_API_KEY"),
        # max_tokens=int(os.getenv("MAX_TOKENS", 20000)),
        top_p=float(os.getenv("TOP_P", 0.8)),
        frequency_penalty=float(os.getenv("FREQUENCY_PENALTY", 0.0)),
        presence_penalty=float(os.getenv("PRESENCE_PENALTY", 0.0)),
        timeout=float(os.getenv("REQUEST_TIMEOUT", 30.0)),
        max_retries=int(os.getenv("MAX_RETRIES", 3)),
        streaming=os.getenv("STREAMING", "True").lower() == "true",
        # 将额外参数通过 extra_body 传递
        extra_body={},
    )

    result_data = state["execution_result"]
    chart_agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=f"""
        你是一位经验丰富的BI专家，必须严格按照以下步骤操作，并且必须调用MCP图表工具：

        ### 重要说明
        - 你必须调用可用的MCP图表工具来生成图表，这是强制要求
        - 不允许返回默认示例链接或虚构链接
        - 如果工具调用失败，请明确说明失败原因

        ### 任务步骤
        1. **分析数据特征**：仔细理解输入数据结构
        2. **调用工具**：必须使用"{chart_type}"工具进行图表渲染
        3. **填充参数**：根据数据特征填充图表参数
        4. **生成图表**：调用MCP工具并等待真实响应
        5. **返回结果**：只返回真实的图表链接

        ### 输入数据
        {result_data}

        ### 严格要求
        - 必须实际调用MCP工具，不能模拟或假设
        - 必须返回真实的图表链接，不能返回示例链接
        - x轴和y轴标签使用中文
        - 如果无法生成图表，请说明具体原因

        ### 返回格式
        ![图表](真实的图表链接)
        """,
    )

    result = await chart_agent.ainvoke(
        {"messages": [("user", "根据输入数据选择合适的MCP图表工具进行渲染")]},
        config={"configurable": {"thread_id": "chart-render"}},
    )

    logging.info(f"图表代理调用结果: {result}")

    state["chart_url"] = result["messages"][-1].content

    return state


def _map_chart_type(chart_type: str) -> str:
    """将AntV的图表工具名称映射为Apache处理模块使用的类型编码"""
    if not chart_type:
        return "response_table"
    ct = chart_type.lower()
    if "generate_column_chart" in ct or "generate_bar_chart" in ct:
        return "response_bar_chart"
    if "generate_line_chart" in ct or "generate_area_chart" in ct or "generate_dual_axes_chart" in ct:
        return "response_line_chart"
    if "generate_pie_chart" in ct:
        return "response_pie_chart"
    return "response_table"
