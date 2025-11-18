# 第6章 CommonReact Agent 实战:MCP 工具集成与多轮对话记忆

## 章节目标

1. 理解 ReAct 模式(Reasoning + Acting)的工作原理,掌握工具调用的思维链路
2. 学会集成 MCP(Model Context Protocol)工具,实现标准化的工具调用接口
3. 掌握 LangGraph 的 Checkpointer 机制,实现跨请求的多轮对话记忆
4. 实践流式输出(SSE)技术,提升用户体验
5. 实现任务取消机制,支持用户中断长时间运行的任务

## 一、ReAct 模式:让 AI 既能思考又能行动

### 1.1 什么是 ReAct

**ReAct = Reasoning(推理) + Acting(行动)**

传统 LLM:
```
用户:"今天北京天气怎么样?"
LLM:"根据我的训练数据(截止2023年),我无法获取实时天气信息。"
```

ReAct Agent:
```
用户:"今天北京天气怎么样?"

[思考] 我需要查询实时天气信息,应该调用天气查询工具
[行动] 调用 get_weather(city="北京")
[观察] 工具返回:晴天,温度 22°C,湿度 45%
[思考] 我已经获取到了天气信息,可以回答用户了
[回答] 今天北京天气晴朗,温度 22°C,湿度 45%,适合外出活动。
```

**核心优势:**
1. **实时性**: 通过工具获取最新信息
2. **可信度**: 工具调用结果可追溯
3. **能力扩展**: 通过添加工具扩展能力边界

### 1.2 ReAct 工作流程

```
┌─────────────┐
│  用户输入   │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  LLM 推理       │
│ "需要工具吗?"  │
└──────┬──────────┘
       │
       ├─────────────┐
       │             │
       ▼             ▼
    需要工具      不需要工具
       │             │
       ▼             │
┌─────────────────┐ │
│  调用工具       │ │
│ (get_weather)  │ │
└──────┬──────────┘ │
       │             │
       ▼             │
┌─────────────────┐ │
│  LLM 综合       │◄┘
│  工具结果回答   │
└──────┬──────────┘
       │
       ▼
┌─────────────┐
│  返回用户   │
└─────────────┘
```

---

## 二、MCP(Model Context Protocol):工具调用的统一标准

### 2.1 为什么需要 MCP

**传统工具集成的痛点:**

```python
# 每个工具都需要自定义函数
def get_weather(city: str) -> str:
    api_key = "xxx"
    response = requests.get(f"https://api.weather.com?city={city}&key={api_key}")
    return response.json()

def search_web(query: str) -> str:
    # 不同的API格式
    ...

def query_database(sql: str) -> str:
    # 又是不同的调用方式
    ...

# 需要手动注册工具
tools = [
    Tool(name="get_weather", func=get_weather, description="查询天气"),
    Tool(name="search_web", func=search_web, description="搜索网页"),
    Tool(name="query_database", func=query_database, description="查询数据库"),
]
```

**MCP 统一标准:**

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

# 统一配置
server_configs = {
    "mcp-hub": {
        "url": "https://mcp-hub.example.com",
        "transport": "sse"
    },
    "mcp-server-chart": {
        "command": "npx",
        "args": ["-y", "@antv/mcp-server-chart"],
        "transport": "stdio"
    }
}

client = MultiServerMCPClient(server_configs)
tools = await client.get_tools()  # 自动获取所有工具
```

**MCP 优势:**
1. **标准化**: 所有工具遵循相同的协议
2. **即插即用**: 无需编写适配代码
3. **远程调用**: 支持 HTTP/SSE 等传输方式
4. **类型安全**: 工具参数自动校验

### 2.2 MCP 架构

```
┌──────────────┐
│   LangChain  │
│    Agent     │
└──────┬───────┘
       │ 请求工具列表
       ▼
┌──────────────────┐
│  MCP Client      │
│ (MultiServer)    │
└──────┬───────────┘
       │
       ├───────────────┬───────────────┐
       │               │               │
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ MCP Server1 │ │ MCP Server2 │ │ MCP Server3 │
│  (天气)     │ │  (图表)     │ │  (搜索)     │
└─────────────┘ └─────────────┘ └─────────────┘
```

### 2.3 项目实战:集成 AntV 图表工具

**配置 MCP Server(`agent/common_react_agent.py:60`):**

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

server_configs = {}

# 配置1: HTTP MCP 服务器(自建)
if os.getenv("MCP_HUB_COMMON_QA_GROUP_URL"):
    server_configs["mcp-hub"] = {
        "url": os.getenv("MCP_HUB_COMMON_QA_GROUP_URL"),
        "transport": "sse",  # Server-Sent Events
    }

# 配置2: stdio MCP 服务器(NPM 包)
server_configs["mcp-server-chart"] = {
    "command": "npx",  # 使用 npx 运行 NPM 包
    "args": ["-y", "@antv/mcp-server-chart"],  # AntV 官方图表工具
    "transport": "stdio",  # 标准输入输出
}

self.client = MultiServerMCPClient(server_configs)
```

**获取工具并创建 Agent:**

```python
# 获取所有工具
tools = await self.client.get_tools()

# 创建 React Agent
from langgraph.prebuilt import create_react_agent

agent = create_react_agent(
    model=self.llm,
    tools=tools,  # 传入 MCP 工具
    prompt=system_message,
    checkpointer=self.checkpointer
)
```

**工具调用示例:**

用户输入:
```
"请绘制一个柱状图,显示各省份的销售额"
```

Agent 推理过程:
```
[思考] 用户要求绘制柱状图,我需要调用 @antv/mcp-server-chart 的工具
[行动] 调用 mcp-server-chart-generate_column_chart({
    "data": [
        {"category": "北京", "value": 1200},
        {"category": "上海", "value": 1500},
        {"category": "广东", "value": 1800}
    ],
    "xField": "category",
    "yField": "value"
})
[观察] 工具返回图表URL: https://chart.example.com/abc123.png
[回答] 已生成柱状图:[图表链接]
```

---

## 三、多轮对话记忆:Checkpointer 机制

### 3.1 无记忆 vs 有记忆

**无记忆(每次都是新对话):**

```
用户:"我叫张三"
Agent:"你好,很高兴认识你!"

用户:"我叫什么名字?"
Agent:"抱歉,我不知道你的名字。"  ❌ 忘记了前面的对话
```

**有记忆(跨请求保持上下文):**

```
用户:"我叫张三"
Agent:"你好张三,很高兴认识你!"

用户:"我叫什么名字?"
Agent:"你叫张三。"  ✅ 记住了前面的对话
```

### 3.2 LangGraph Checkpointer 原理

**数据结构:**

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()

# 内部存储结构(简化版):
{
    "thread_id_1": {  # 用户A的对话
        "messages": [
            HumanMessage("我叫张三"),
            AIMessage("你好张三"),
            HumanMessage("我叫什么名字?"),
            AIMessage("你叫张三")
        ]
    },
    "thread_id_2": {  # 用户B的对话
        "messages": [
            HumanMessage("今天天气怎么样?"),
            AIMessage("...")
        ]
    }
}
```

**使用方法:**

```python
# 创建全局 checkpointer
self.checkpointer = InMemorySaver()

# 创建 agent 时传入
agent = create_react_agent(
    model=self.llm,
    tools=tools,
    checkpointer=self.checkpointer  # 传入记忆管理器
)

# 执行时指定 thread_id
config = {"configurable": {"thread_id": "user_123"}}
agent.invoke({"messages": [HumanMessage("我叫张三")]}, config=config)
agent.invoke({"messages": [HumanMessage("我叫什么?")]}, config=config)
# 第二次调用会自动加载 thread_id="user_123" 的历史消息
```

### 3.3 项目实战:按会话隔离对话

**初始化 Checkpointer(`agent/common_react_agent.py:74`):**

```python
from langgraph.checkpoint.memory import InMemorySaver

class LangGraphReactAgent:
    def __init__(self):
        # ... 其他初始化代码 ...

        # 全局checkpointer用于持久化所有用户的对话状态
        self.checkpointer = InMemorySaver()
```

**执行时指定会话ID(`agent/common_react_agent.py:159`):**

```python
async def run_agent(
    self,
    query: str,
    response,
    session_id: Optional[str] = None,  # 会话ID
    uuid_str: str = None,
    user_token=None,
):
    # 使用用户会话ID作为thread_id,如果未提供则使用默认值
    thread_id = session_id if session_id else "default_thread"
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}

    # 创建 agent
    agent = create_react_agent(
        model=self.llm,
        tools=tools,
        prompt=system_message,
        checkpointer=self.checkpointer,  # 传入记忆管理器
    )

    # 执行(自动加载该thread_id的历史消息)
    async for message_chunk, metadata in agent.astream(
        input={"messages": [HumanMessage(content=query)]},
        config=config,  # 传入配置
        stream_mode="messages",
    ):
        # 处理输出
        ...
```

**前端传递会话ID:**

```javascript
// 前端生成唯一会话ID
const sessionId = localStorage.getItem("chat_session_id") ||
                  crypto.randomUUID();
localStorage.setItem("chat_session_id", sessionId);

// 请求时携带
fetch("/api/chat", {
    method: "POST",
    body: JSON.stringify({
        query: "我叫张三",
        session_id: sessionId  // 传递会话ID
    })
});
```

### 3.4 消息修剪(Trim Messages)

**问题:** 对话历史越来越长,超过模型上下文窗口

**解决方案:短期记忆策略**

```python
from langchain_core.messages.utils import trim_messages

@staticmethod
def short_trim_messages(state):
    """
    模型调用前的消息清理钩子函数
    短期记忆:限制模型调用前的消息数量,只保留最近的若干条消息
    """
    trimmed_messages = trim_messages(
        messages=state["messages"],
        max_tokens=50000,  # 最大token数
        token_counter=lambda messages: sum(len(msg.content or "") for msg in messages),
        strategy="last",  # 保留最新的消息
        allow_partial=False,
        start_on="human",  # 确保从人类消息开始
        include_system=True,  # 包含系统消息
    )

    return {"llm_input_messages": trimmed_messages}

# 在创建agent时传入
agent = create_react_agent(
    model=self.llm,
    tools=tools,
    checkpointer=self.checkpointer,
    pre_model_hook=short_trim_messages  # 传入钩子函数
)
```

**修剪策略:**
- `strategy="last"`: 保留最新的 N 条消息
- `strategy="first"`: 保留最早的 N 条消息
- `include_system=True`: 始终保留系统提示词
- `start_on="human"`: 确保对话从用户消息开始(避免 AI 自言自语)

---

## 四、流式输出(SSE):实时反馈提升体验

### 4.1 为什么需要流式输出

**非流式输出(用户需要等待完整结果):**

```
用户:"写一篇500字的文章"
[等待 30 秒...]
Agent:"这是一篇关于... [500字内容]"
```

**流式输出(边生成边显示):**

```
用户:"写一篇500字的文章"
Agent:"这"
Agent:"是"
Agent:"一"
Agent:"篇"
Agent:"关"
Agent:"于"
...
```

**优势:**
1. **即时反馈**: 用户知道系统在工作
2. **可中断**: 用户可以提前停止
3. **体验更好**: 类似打字机效果

### 4.2 SSE(Server-Sent Events) 技术

**传统HTTP vs SSE:**

```
传统HTTP:
客户端 → 请求 → 服务器
客户端 ← 响应 ← 服务器
[连接关闭]

SSE:
客户端 → 请求 → 服务器
客户端 ← 数据流1 ← 服务器
客户端 ← 数据流2 ← 服务器
客户端 ← 数据流3 ← 服务器
...
[保持连接]
```

**Sanic 实现SSE:**

```python
from sanic.response import stream

@app.post("/api/chat/stream")
@async_json_resp
async def chat_stream(request):
    query = request.json.get("query")

    async def streaming_fn(response):
        # 设置SSE headers
        response.headers["Content-Type"] = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"

        # 流式写入
        await response.write("data: 你\n\n")
        await response.write("data: 好\n\n")
        await response.write("data: [DONE]\n\n")

    return stream(streaming_fn)
```

### 4.3 项目实战:流式返回 Agent 输出

**Agent 流式执行(`agent/common_react_agent.py:282`):**

```python
async def run_agent(self, query: str, response, session_id: str, ...):
    """运行智能体,支持流式输出"""

    # 流式执行 agent
    async for message_chunk, metadata in agent.astream(
        input={"messages": [HumanMessage(content=query)]},
        config=config,
        stream_mode="messages",  # 按消息流式返回
    ):
        # 检查是否已取消
        if self.running_tasks[task_id]["cancelled"]:
            await response.write(
                self._create_response("\n> 这条消息已停止", "info")
            )
            break

        # 工具调用输出
        if metadata["langgraph_node"] == "tools":
            tool_name = message_chunk.name or "未知工具"
            tool_use = f"> 调用工具:{tool_name}\n\n"
            await response.write(self._create_response(tool_use))
            continue

        # LLM 输出
        if message_chunk.content:
            content = message_chunk.content
            await response.write(self._create_response(content))

            # 确保实时输出
            if hasattr(response, "flush"):
                await response.flush()
            await asyncio.sleep(0)
```

**响应格式封装(`agent/common_react_agent.py:80`):**

```python
@staticmethod
def _create_response(
    content: str,
    message_type: str = "continue",
    data_type: str = DataTypeEnum.ANSWER.value[0]
) -> str:
    """封装SSE响应结构"""
    res = {
        "data": {
            "messageType": message_type,  # continue/info/end
            "content": content
        },
        "dataType": data_type,  # t02/t04等
    }
    return "data:" + json.dumps(res, ensure_ascii=False) + "\n\n"
```

**前端接收流式数据:**

```javascript
const eventSource = new EventSource("/api/chat/stream");

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.data.messageType === "continue") {
        // 追加内容到界面
        document.getElementById("output").innerText += data.data.content;
    } else if (data.dataType === "t99") {
        // 流结束
        eventSource.close();
    }
};
```

---

## 五、任务取消机制:优雅中断长时间任务

### 5.1 为什么需要任务取消

**场景:**
```
用户:"写一篇10000字的科幻小说"
[Agent 开始生成,已经写了 2000 字...]
用户:"停止!我不需要了"
[但是 Agent 仍然继续写到 10000 字]  ❌ 浪费资源
```

**解决方案:**
```
用户:"写一篇10000字的科幻小说"
[Agent 开始生成,已经写了 2000 字...]
用户:"停止!"
[Agent 立即停止,清理资源]  ✅ 节省成本
```

### 5.2 任务取消的实现

**核心思路:轮询检查取消标志**

```python
class LangGraphReactAgent:
    def __init__(self):
        # 存储运行中的任务
        self.running_tasks = {}

    async def run_agent(self, ...):
        # 获取用户ID作为任务ID
        user_dict = await decode_jwt_token(user_token)
        task_id = user_dict["id"]

        # 创建任务上下文
        task_context = {"cancelled": False}
        self.running_tasks[task_id] = task_context

        try:
            async for message_chunk, metadata in agent.astream(...):
                # 检查是否已取消
                if self.running_tasks[task_id]["cancelled"]:
                    await response.write(
                        self._create_response("\n> 这条消息已停止", "info")
                    )
                    break  # 退出循环

                # 处理消息...
                await response.write(self._create_response(content))

        finally:
            # 清理任务记录
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]

    async def cancel_task(self, task_id: str) -> bool:
        """取消指定的任务"""
        if task_id in self.running_tasks:
            self.running_tasks[task_id]["cancelled"] = True
            return True
        return False
```

**取消任务的API:**

```python
@bp.post("/api/chat/cancel")
@async_json_resp
async def cancel_chat(request):
    user_info = await get_user_info(request)
    task_id = user_info["id"]

    # 调用agent的取消方法
    success = await react_agent.cancel_task(task_id)

    return {"cancelled": success}
```

**前端调用:**

```javascript
// 用户点击停止按钮
document.getElementById("stop-btn").addEventListener("click", async () => {
    await fetch("/api/chat/cancel", { method: "POST" });
    eventSource.close();  // 关闭SSE连接
});
```

---

## 六、完整代码解析

### 6.1 LangGraphReactAgent 类结构

**完整源码(`agent/common_react_agent.py`,共 362 行):**

```python
import asyncio
import json
import logging
import os
from typing import Optional

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.messages.utils import trim_messages
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from constants.code_enum import DataTypeEnum, DiFyAppEnum
from services.user_service import add_user_record, decode_jwt_token

logger = logging.getLogger(__name__)


class LangGraphReactAgent:
    """
    基于LangGraph的React智能体,支持多轮对话记忆
    """

    def __init__(self):
        # 校验并获取环境变量
        required_env_vars = [
            "MODEL_NAME",
            "MODEL_TEMPERATURE",
            "MODEL_BASE_URL",
            "MODEL_API_KEY",
        ]
        for var in required_env_vars:
            if not os.getenv(var):
                raise ValueError(f"Missing required environment variable: {var}")

        # 初始化LLM
        self.llm = ChatOpenAI(
            model=os.getenv("MODEL_NAME", "qwen-plus"),
            temperature=float(os.getenv("MODEL_TEMPERATURE", 0.75)),
            base_url=os.getenv("MODEL_BASE_URL"),
            api_key=os.getenv("MODEL_API_KEY"),
            max_tokens=int(os.getenv("MAX_TOKENS", 100000)),
            top_p=float(os.getenv("TOP_P", 0.8)),
            streaming=True,
        )

        # 配置MCP工具服务器
        server_configs = {}
        if os.getenv("MCP_HUB_COMMON_QA_GROUP_URL"):
            server_configs["mcp-hub"] = {
                "url": os.getenv("MCP_HUB_COMMON_QA_GROUP_URL"),
                "transport": "sse",
            }
        server_configs["mcp-server-chart"] = {
            "command": "npx",
            "args": ["-y", "@antv/mcp-server-chart"],
            "transport": "stdio",
        }
        self.client = MultiServerMCPClient(server_configs)

        # 全局checkpointer用于持久化所有用户的对话状态
        self.checkpointer = InMemorySaver()

        # 存储运行中的任务
        self.running_tasks = {}

    @staticmethod
    def _create_response(
        content: str,
        message_type: str = "continue",
        data_type: str = DataTypeEnum.ANSWER.value[0]
    ) -> str:
        """封装响应结构"""
        res = {
            "data": {"messageType": message_type, "content": content},
            "dataType": data_type,
        }
        return "data:" + json.dumps(res, ensure_ascii=False) + "\n\n"

    @staticmethod
    def short_trim_messages(state):
        """
        模型调用前的消息清理钩子函数
        短期记忆:限制模型调用前的消息数量
        """
        trimmed_messages = trim_messages(
            messages=state["messages"],
            max_tokens=50000,
            token_counter=lambda messages: sum(len(msg.content or "") for msg in messages),
            strategy="last",  # 保留最新的消息
            allow_partial=False,
            start_on="human",  # 确保从人类消息开始
            include_system=True,  # 包含系统消息
        )

        return {"llm_input_messages": trimmed_messages}

    async def run_agent(
        self,
        query: str,
        response,
        session_id: Optional[str] = None,
        uuid_str: str = None,
        user_token=None,
        file_list: dict = None,
    ):
        """运行智能体,支持多轮对话记忆"""

        # 获取用户信息 标识对话状态
        user_dict = await decode_jwt_token(user_token)
        task_id = user_dict["id"]
        task_context = {"cancelled": False}
        self.running_tasks[task_id] = task_context

        try:
            t02_answer_data = []

            # 获取MCP工具
            try:
                tools = await self.client.get_tools()
            except Exception:
                # 降级处理
                tools = []
                await response.write(
                    self._create_response(
                        "> MCP工具不可用,改为纯模型应答",
                        "info"
                    )
                )

            # 使用用户会话ID作为thread_id
            thread_id = session_id if session_id else "default_thread"
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 50
            }

            # 系统提示词
            system_message = SystemMessage(
                content="""
            # Role: 高级AI助手

            ## Profile
            - language: 中文
            - description: 一位具备多领域知识、高度专业性与结构化输出能力的智能助手

            ## Skills
            1. 信息处理与表达
               - 精准应答
               - 结构化输出
               - 语言适配

            2. 工具协作与交互
               - 工具调用提示
               - 操作透明化
               - 多模态支持

            ## Rules
            1. 基本原则:
               - 准确性优先
               - 用户导向
               - 透明性
               - 可读性

            2. 关键规则
                1. 在完成用户请求后必须直接输出最终答案,不要进行额外的操作
                2. 避免无意义的重复工具调用
                3. 当不需要调用工具时,直接回答用户问题
                4. 在完成任务后立即停止

            ## Workflows
            - 目标: 提供准确、结构清晰的高质量回答
            - 步骤 1: 理解用户意图
            - 步骤 2: 检索知识库,判断是否需要调用工具
            - 步骤 3: 生成内容并优化

            ## OutputFormat
            - format: markdown
            - structure: 分节说明,层级清晰
            - style: 专业、简洁、结构化
            """
            )

            # 创建React Agent
            agent = create_react_agent(
                model=self.llm,
                tools=tools,
                prompt=system_message,
                checkpointer=self.checkpointer,
                pre_model_hook=self.short_trim_messages,
            )

            # 流式执行
            async for message_chunk, metadata in agent.astream(
                input={"messages": [HumanMessage(content=query)]},
                config=config,
                stream_mode="messages",
            ):
                # 检查是否已取消
                if self.running_tasks[task_id]["cancelled"]:
                    await response.write(
                        self._create_response("\n> 这条消息已停止", "info")
                    )
                    break

                # 工具输出
                if metadata["langgraph_node"] == "tools":
                    tool_name = message_chunk.name or "未知工具"
                    tool_use = f"> 调用工具:{tool_name}\n\n"
                    await response.write(self._create_response(tool_use))
                    t02_answer_data.append(tool_use)
                    continue

                # LLM输出
                if message_chunk.content:
                    content = message_chunk.content
                    t02_answer_data.append(content)
                    await response.write(self._create_response(content))

                    # 确保实时输出
                    if hasattr(response, "flush"):
                        await response.flush()
                    await asyncio.sleep(0)

            # 只有在未取消的情况下才保存记录
            if not self.running_tasks[task_id]["cancelled"]:
                await add_user_record(
                    uuid_str,
                    session_id,
                    query,
                    t02_answer_data,
                    {},
                    DiFyAppEnum.COMMON_QA.value[0],
                    user_token,
                    file_list,
                )

        except asyncio.CancelledError:
            await response.write(
                self._create_response("\n> 这条消息已停止", "info")
            )
        except Exception as e:
            logger.error(f"[ERROR] Agent运行异常: {e}")
            await response.write(
                self._create_response("[ERROR] 智能体运行异常:", "error")
            )
        finally:
            # 清理任务记录
            if task_id in self.running_tasks:
                del self.running_tasks[task_id]

    async def cancel_task(self, task_id: str) -> bool:
        """取消指定的任务"""
        if task_id in self.running_tasks:
            self.running_tasks[task_id]["cancelled"] = True
            return True
        return False

    def get_running_tasks(self):
        """获取当前运行中的任务列表"""
        return list(self.running_tasks.keys())
```

### 6.2 关键代码段解析

**1. MCP 工具获取与降级处理:**

```python
try:
    tools = await self.client.get_tools()
except Exception:
    # 降级:MCP服务不可用时,使用备用配置
    try:
        fallback_client = MultiServerMCPClient({
            "mcp-server-chart": {
                "command": "npx",
                "args": ["-y", "@antv/mcp-server-chart"],
                "transport": "stdio",
            }
        })
        tools = await fallback_client.get_tools()
    except Exception:
        # 完全降级:无工具模式
        tools = []
        await response.write(
            self._create_response("> MCP工具不可用,改为纯模型应答", "info")
        )
```

**2. 流式输出分类处理:**

```python
# 工具调用时的输出
if metadata["langgraph_node"] == "tools":
    tool_name = message_chunk.name or "未知工具"
    tool_use = f"> 调用工具:{tool_name}\n\n"
    await response.write(self._create_response(tool_use))
    continue

# LLM 生成的输出
if message_chunk.content:
    content = message_chunk.content
    await response.write(self._create_response(content))
```

---

## 七、本章总结

### 7.1 核心要点回顾

1. **ReAct 模式**: Reasoning(思考) + Acting(工具调用) 的协同工作
2. **MCP 标准**: 统一工具调用接口,支持 HTTP/SSE/stdio 传输
3. **多轮对话**: 通过 Checkpointer 实现跨请求的上下文记忆
4. **流式输出**: SSE 技术提升用户体验
5. **任务取消**: 轮询检查标志位,优雅中断长时间任务

### 7.2 最佳实践

1. **工具降级**: MCP 服务不可用时提供备用方案
2. **消息修剪**: 使用 `trim_messages` 避免超过上下文窗口
3. **异常隔离**: 每个模块独立捕获异常,不影响全局
4. **资源清理**: 使用 `finally` 确保任务记录被清理

### 7.3 下一章预告

下一章我们将深入 **Text2SQL Agent 第一部分:BM25 + 向量混合检索**,学习如何:
- 使用 BM25 进行关键词匹配
- 构建 FAISS 向量索引
- RRF 融合多种检索结果
- DashScope Rerank 重排序优化

---

**完整文件清单:**
- `agent/common_react_agent.py` (362 行) - CommonReact Agent 完整实现
