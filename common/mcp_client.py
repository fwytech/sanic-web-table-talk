import asyncio
import json
import logging
from typing import Optional

from mcp import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)


class MCPClient:
    """
    MCP客户端工具类
    """

    def __init__(self, server_url: str):
        # 初始化会话和客户端对象
        self.session: Optional[ClientSession] = None
        self._streams_context = None
        self._session_context = None
        self._server_url = server_url

    async def connect_to_sse_server(self):
        """连接到运行SSE传输的MCP服务器"""
        try:
            # 保存上下文管理器以保持其活跃状态
            self._streams_context = sse_client(url=self._server_url)
            streams = await self._streams_context.__aenter__()

            self._session_context = ClientSession(*streams)
            self.session: ClientSession = await self._session_context.__aenter__()

            # 初始化
            await self.session.initialize()

            # 列出可用工具以验证连接
            logger.info("已初始化SSE客户端...")
            response = await self.session.list_tools()
            tools = response.tools
            logger.info("\nMCP server提供的工具：")
            for tool in tools:
                logger.info(f"- {tool.name}: {tool.description}")

            # 转换工具格式并打印
            formatted_tools = self._format_tools(tools)

            logger.info("\n转换后的工具格式：")
            print(json.dumps(formatted_tools, indent=2, ensure_ascii=False))
            return formatted_tools, self.session
        except Exception as e:
            # 初始化失败时主动清理资源
            await self.cleanup()
            raise e

    @staticmethod
    def _format_tools(tools):
        """将MCP工具格式转换为OpenAI工具格式"""
        formatted_tools = []
        for tool in tools:
            # 构建参数属性
            properties = {}
            for param_name, param_info in tool.inputSchema["properties"].items():
                param_data = {
                    "type": param_info["type"],
                    "description": param_info.get("description"),
                }

                # 如果是数组类型，添加items
                if param_info["type"] == "array" and "items" in param_info:
                    param_data["items"] = {"type": param_info["items"]["type"]}

                properties[param_name] = param_data

            # 使用工具名作为key
            tool_dict = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": tool.inputSchema.get("required", []),
                    },
                },
            }

            # 存储工具配置到 formatted_tools
            formatted_tools.append(tool_dict)
        return formatted_tools

    async def cleanup(self):
        """正确清理会话和流"""
        if self._session_context:
            await self._session_context.__aexit__(None, None, None)
            self._session_context = None
        if self._streams_context:
            await self._streams_context.__aexit__(None, None, None)
            self._streams_context = None


async def execute_tool_call(session, tool_name, tool_args):
    """执行单个工具调用"""
    try:
        # 使用session的call_tool方法来调用工具
        tool_response = await session.call_tool(tool_name, tool_args)

        # 处理工具响应
        if tool_response.isError:
            # 如果是错误响应，获取错误信息
            error_message = tool_response.content[0].text if tool_response.content else "未知错误"
            logger.info(f"工具 {tool_name} 执行错误: {error_message}")
            return {
                "status": "error",
                "message": "工具执行出错",
                "details": error_message,
                "suggestion": "这可能是临时性问题，您可以：\n1. 尝试重新查询\n2. 换个不同的查询方式\n3. 使用其他可用的工具",
            }
        else:
            # 如果是正常响应，获取响应内容
            result = tool_response.content[0].text if tool_response.content else ""
            logger.info(f"工具 {tool_name} 执行成功: {result}")
            return {
                "status": "success",
                "result": result,
            }
    except Exception as e:
        logger.info(f"工具 {tool_name} 调用异常: {str(e)}")
        return {
            "status": "error",
            "message": "工具调用异常",
            "details": str(e),
            "suggestion": "这是一个意外错误，请稍后重试或联系管理员",
        }


async def main():
    client = MCPClient(server_url="http://localhost:3300/sse")
    try:
        model = "qwen-plus"
        available_tools, session = await client.connect_to_sse_server()
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
