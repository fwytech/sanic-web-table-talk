# 第5章 LangChain 与 LangGraph 核心概念:从传统函数到状态图的范式转变

## 章节目标

1. 理解 LangChain 的链式调用机制,掌握 Prompt + LLM + OutputParser 的组合模式
2. 学会 LangGraph 的状态图设计哲学,用节点+边替代复杂的 if-else 逻辑
3. 掌握 TypedDict 定义状态的最佳实践,实现类型安全的数据流转
4. 通过对比传统代码与 LangGraph 实现,理解其在复杂业务场景下的优势

## 一、为什么需要 LangChain/LangGraph

### 1.1 传统 LLM 调用的痛点

**反面案例(直接调用 OpenAI API):**
```python
import openai

def ask_llm(question):
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": question}
        ]
    )
    return response.choices[0].message.content

# 问题1: 每次都要手动构建 messages 格式
# 问题2: 无法复用提示词模板
# 问题3: 多轮对话需要手动管理历史记录
# 问题4: 错误处理、重试逻辑需要自己实现
```

**LangChain 解决方案:**
```python
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# 提示词模板化
prompt = ChatPromptTemplate.from_template("你是一个{role},请回答:{question}")
llm = ChatOpenAI(model="gpt-4")

# 链式调用
chain = prompt | llm  # LCEL (LangChain Expression Language)
response = chain.invoke({"role": "数据分析师", "question": "如何优化SQL查询?"})
```

**三大优势:**
1. **模板化**: 提示词可复用,变量自动替换
2. **链式组合**: 通过 `|` 管道符串联多个组件
3. **统一接口**: 不同 LLM 提供商使用相同的 API

### 1.2 传统流程控制的局限性

**场景:** Text2SQL 智能体需要按以下步骤执行:
1. 检索相关表结构
2. 生成 SQL
3. 执行 SQL
4. 总结结果
5. 生成图表

**传统写法(if-else 嵌套地狱):**
```python
async def text2sql_pipeline(user_query):
    # 步骤1: 检索表结构
    db_info = await get_table_schema(user_query)
    if not db_info:
        return "未找到相关表"

    # 步骤2: 生成 SQL
    sql = await generate_sql(user_query, db_info)
    if not sql:
        return "SQL生成失败"

    # 步骤3: 执行 SQL
    result = await execute_sql(sql)
    if not result.success:
        # 修正 SQL 并重试
        corrected_sql = await correct_sql(sql, result.error)
        result = await execute_sql(corrected_sql)
        if not result.success:
            return "SQL执行失败"

    # 步骤4: 总结
    summary = await summarize(result.data)

    # 步骤5: 生成图表
    if is_chart_needed(user_query):
        chart = await generate_chart(result.data)
        return {"summary": summary, "chart": chart}
    else:
        return {"summary": summary}

# 问题:
# 1. 代码嵌套层级深,难以维护
# 2. 错误处理逻辑分散
# 3. 难以可视化整个流程
# 4. 难以动态调整步骤顺序
```

**LangGraph 解决方案(状态图):**
```python
from langgraph.graph import StateGraph, END

# 定义状态
class AgentState(TypedDict):
    user_query: str
    db_info: Optional[Dict]
    generated_sql: Optional[str]
    execution_result: Optional[ExecutionResult]
    report_summary: Optional[str]
    chart_url: Optional[str]

# 创建状态图
graph = StateGraph(AgentState)

# 添加节点
graph.add_node("schema_inspector", get_table_schema)
graph.add_node("sql_generator", generate_sql)
graph.add_node("sql_executor", execute_sql)
graph.add_node("summarize", summarize)
graph.add_node("data_render", generate_chart)

# 添加边(定义执行顺序)
graph.set_entry_point("schema_inspector")
graph.add_edge("schema_inspector", "sql_generator")
graph.add_edge("sql_generator", "sql_executor")
graph.add_edge("sql_executor", "summarize")
graph.add_conditional_edges(
    "summarize",
    lambda state: "data_render" if state.get("chart_url") else END
)

graph_compiled = graph.compile()

# 执行
result = await graph_compiled.ainvoke({"user_query": "统计订单数据"})
```

**优势:**
1. **可视化**: 可以生成流程图(Mermaid)
2. **模块化**: 每个节点独立测试
3. **灵活性**: 通过条件边动态路由
4. **可观测**: 内置状态追踪

---

## 二、LangChain 核心概念

### 2.1 Prompt Template(提示词模板)

**基本用法:**
```python
from langchain.prompts import ChatPromptTemplate

# 方式1: 简单字符串模板
prompt = ChatPromptTemplate.from_template(
    "你是一个{role},请回答:{question}"
)

# 方式2: 多轮对话模板
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个专业的{role}"),
    ("human", "{question}"),
    ("ai", "我理解你的问题,让我分析一下..."),
    ("human", "请继续")
])

# 调用
formatted = prompt.format(role="DBA", question="如何优化索引?")
print(formatted)
```

**项目实战示例(`agent/text2sql/sql/generator.py:17`):**
```python
from langchain.prompts import ChatPromptTemplate

def sql_generate(state):
    llm = get_llm()

    prompt = ChatPromptTemplate.from_template(
        """
        你是一位专业的数据库管理员(DBA),任务是根据提供的数据库结构、表关系以及用户需求,生成优化的MYSQL SQL查询语句。

        ## 任务
          - 根据用户问题生成一条优化的SQL语句。
          - 从图表定义中选择最合适的图表类型。

        ## 约束条件
         1. 你必须仅生成一条合法、可执行的SQL查询语句。
         2. 必须直接使用所提供的表结构和表关系来生成SQL语句。
         3. 使用适当的SQL子句(JOIN、WHERE、GROUP BY、HAVING等)。
         4. 如果用户问题模糊,请返回:`NULL`

       ## 提供的信息
        - 表结构:{db_schema}
        - 表关系:{table_relationship}
        - 用户提问:{user_query}
        - 当前时间:{current_time}

        ## 输出格式
        {{
            "sql_query": "生成的SQL语句",
            "chart_type": "推荐的图表类型"
        }}
    """
    )

    chain = prompt | llm

    response = chain.invoke({
        "db_schema": state["db_info"],
        "user_query": state["user_query"],
        "table_relationship": state.get("table_relationship", []),
        "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    # 解析 JSON 响应
    clean_json_str = response.content.strip().removeprefix("```json").strip().removesuffix("```").strip()
    result = json.loads(clean_json_str)
    state["generated_sql"] = result["sql_query"]
    state["chart_type"] = result["chart_type"]

    return state
```

**关键设计点:**
1. **多层次约束**: 任务 → 约束条件 → 输出格式,引导 LLM 生成符合要求的结果
2. **上下文注入**: 将 `db_schema`、`user_query` 等动态信息传入
3. **结构化输出**: 强制要求 JSON 格式,方便后续解析

### 2.2 LLM 调用与配置

**统一 LLM 配置(`common/llm_util.py`):**
```python
import os
from langchain_openai import ChatOpenAI

def get_llm():
    """获取统一配置的 LLM 实例"""
    return ChatOpenAI(
        model=os.getenv("MODEL_NAME", "qwen-plus"),
        temperature=float(os.getenv("MODEL_TEMPERATURE", 0.75)),
        base_url=os.getenv("MODEL_BASE_URL"),
        api_key=os.getenv("MODEL_API_KEY"),
        max_tokens=int(os.getenv("MAX_TOKENS", 100000)),
        top_p=float(os.getenv("TOP_P", 0.8)),
        timeout=float(os.getenv("REQUEST_TIMEOUT", 300.0)),
        max_retries=int(os.getenv("MAX_RETRIES", 3)),
        streaming=True,  # 流式输出
    )
```

**为什么集中配置:**
1. **环境隔离**: 不同环境(dev/test/pro)使用不同的模型配置
2. **统一管理**: 修改模型参数只需改一处
3. **成本控制**: 可以统一设置 token 限制

**常用参数解析:**
- `temperature`: 温度参数(0-1)
  - 0 = 确定性输出(每次结果相同)
  - 0.7 = 创意与准确性平衡
  - 1 = 最大随机性
- `max_tokens`: 最大输出 token 数
- `top_p`: 核采样参数(0.8 表示从概率累积到 80% 的词中采样)
- `streaming`: 是否流式返回(True 时可实时显示生成过程)

### 2.3 LCEL(LangChain Expression Language) 链式调用

**管道符组合:**
```python
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_template("总结这段文字:{text}")
llm = ChatOpenAI()
output_parser = StrOutputParser()

# 链式组合
chain = prompt | llm | output_parser

# 等价于:
# step1 = prompt.format(text=input_text)
# step2 = llm.invoke(step1)
# step3 = output_parser.parse(step2)

result = chain.invoke({"text": "LangChain 是一个强大的框架..."})
```

**复杂链示例:**
```python
from langchain.schema.runnable import RunnablePassthrough

# 多分支链
chain = (
    {"context": retriever, "question": RunnablePassthrough()}  # 并行执行
    | prompt
    | llm
    | StrOutputParser()
)

# 条件链
from langchain.schema.runnable import RunnableBranch

branch = RunnableBranch(
    (lambda x: "SQL" in x["query"], sql_chain),
    (lambda x: "图表" in x["query"], chart_chain),
    default_chain
)
```

---

## 三、LangGraph 核心概念

### 3.1 State(状态):数据的统一容器

**为什么需要 State:**

传统方式:
```python
# 每个函数都要返回所有中间结果
def step1(query):
    db_info = get_db_info(query)
    return {"query": query, "db_info": db_info}

def step2(data):
    sql = generate_sql(data["query"], data["db_info"])
    return {"query": data["query"], "db_info": data["db_info"], "sql": sql}

# 参数越来越多,容易遗漏
```

LangGraph State:
```python
from typing import TypedDict, Optional

class AgentState(TypedDict):
    """所有步骤共享的状态"""
    user_query: str
    db_info: Optional[Dict]
    generated_sql: Optional[str]
    execution_result: Optional[ExecutionResult]

# 每个节点只需要关注自己需要的字段
def step1(state: AgentState) -> AgentState:
    state["db_info"] = get_db_info(state["user_query"])
    return state  # 自动合并到全局状态

def step2(state: AgentState) -> AgentState:
    state["generated_sql"] = generate_sql(state["user_query"], state["db_info"])
    return state  # 可以访问前面步骤的结果
```

**项目实战(`agent/text2sql/state/agent_state.py:48`):**
```python
from typing import TypedDict, Optional, Dict, List, Any
from pydantic import BaseModel, Field

class ExecutionResult(BaseModel):
    """SQL执行结果"""
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None

class AgentState(TypedDict):
    """Text2SQL 智能体的状态定义"""
    user_query: str  # 用户问题
    db_info: Optional[Dict]  # 数据库信息
    table_relationship: Optional[List[Dict[str, Any]]]  # 表关系
    generated_sql: Optional[str]  # 生成的 SQL
    execution_result: Optional[ExecutionResult]  # SQL 执行结果
    report_summary: Optional[str]  # 报告摘要
    attempts: int = 0  # 尝试次数
    chart_url: Optional[str]  # 图表地址
    chart_type: Optional[str]  # 图表类型
    apache_chart_data: Optional[Dict[str, Any]]  # 图表数据
```

**设计要点:**
1. **类型注解完整**: 使用 `TypedDict` 提供类型提示
2. **Optional 标注**: 初始状态可能为空的字段
3. **业务建模**: 包含尝试次数等控制字段

### 3.2 Node(节点):状态转换函数

**节点的本质:**
```python
# 节点就是一个接收 State 并返回 State 的函数
def my_node(state: AgentState) -> AgentState:
    # 1. 读取需要的状态
    user_query = state["user_query"]

    # 2. 执行业务逻辑
    result = do_something(user_query)

    # 3. 更新状态
    state["some_field"] = result

    # 4. 返回状态
    return state
```

**项目实战(`agent/text2sql/database/db_service.py:479`):**
```python
def get_table_schema(self, state: AgentState) -> AgentState:
    """
    根据用户查询,通过混合检索筛选出最相关的数据库表结构。

    Args:
        state (AgentState): 当前状态,包含 user_query

    Returns:
        AgentState: 更新后的状态,包含 db_info
    """
    try:
        logger.info("🔍 开始获取数据库表 schema 信息")
        all_table_info = self._fetch_all_table_info()

        user_query = state.get("user_query", "").strip()
        if not user_query:
            state["db_info"] = all_table_info
            return state

        # 混合检索:BM25 + 向量检索
        bm25_top_indices = self._retrieve_by_bm25(all_table_info, user_query)
        vector_top_indices = self._retrieve_by_vector(user_query, top_k=20)

        # RRF 融合
        fused_indices = self._rrf_fusion(bm25_top_indices, vector_top_indices)

        # 重排序
        candidate_tables = {self._table_names[i]: all_table_info[self._table_names[i]]
                           for i in fused_indices[:10]}
        reranked_results = self._rerank_with_dashscope(user_query, candidate_tables)

        # 取 top 4
        final_table_names = [name for name, _ in reranked_results][:4]
        filtered_info = {name: all_table_info[name] for name in final_table_names}

        state["db_info"] = filtered_info
        logger.info(f"✅ 最终筛选出 {len(filtered_info)} 个相关表: {list(filtered_info.keys())}")

    except Exception as e:
        logger.error(f"❌ 获取数据库表信息失败: {e}")
        state["db_info"] = {}
        state["execution_result"] = ExecutionResult(success=False, error="无法连接数据库")

    return state
```

**节点设计原则:**
1. **单一职责**: 每个节点只做一件事
2. **无副作用**: 不修改外部变量(只修改 state)
3. **异常处理**: 捕获异常并更新到 state 中
4. **日志记录**: 记录关键步骤便于调试

### 3.3 Edge(边):节点间的连接

**三种边类型:**

**1. 普通边(固定路由):**
```python
graph.add_edge("node_a", "node_b")  # 执行完 node_a 后总是执行 node_b
```

**2. 条件边(动态路由):**
```python
def route_function(state: AgentState) -> str:
    """根据状态决定下一个节点"""
    if state["execution_result"].success:
        return "summarize"
    else:
        return "error_handler"

graph.add_conditional_edges(
    "sql_executor",  # 源节点
    route_function,  # 路由函数
    {
        "summarize": "summarize",  # 路由值 -> 目标节点
        "error_handler": "error_handler"
    }
)
```

**3. 入口/出口点:**
```python
graph.set_entry_point("schema_inspector")  # 起始节点
graph.add_edge("summarize", END)  # END 是特殊节点,表示流程结束
```

**项目实战(`agent/text2sql/analysis/graph.py:18`):**
```python
from langgraph.graph import StateGraph, END

def data_render_condition(state: AgentState) -> str:
    """
    根据 chart_type 判断使用哪种图表渲染方式
    """
    chart_type = state.get("chart_type")
    if not chart_type or chart_type.lower() in ["mcp-server-chart-generate_table"]:
        return "data_render_apache"  # 表格使用 Apache ECharts
    return "data_render"  # 其他图表使用 AntV

def create_graph():
    graph = StateGraph(AgentState)
    db_service = DatabaseService()

    # 添加节点
    graph.add_node("schema_inspector", db_service.get_table_schema)
    graph.add_node("sql_generator", sql_generate)
    graph.add_node("sql_executor", db_service.execute_sql)
    graph.add_node("data_render", data_render_ant)
    graph.add_node("data_render_apache", data_render_apache)
    graph.add_node("summarize", summarize)

    # 添加边
    graph.set_entry_point("schema_inspector")

    # 条件边:是否启用 Neo4j
    neo4j_enabled = os.getenv("NEO4J_ENABLED", "false").lower() == "true"
    if neo4j_enabled:
        graph.add_node("table_relationship", get_table_relationship)
        graph.add_edge("schema_inspector", "table_relationship")
        graph.add_edge("table_relationship", "sql_generator")
    else:
        graph.add_edge("schema_inspector", "sql_generator")

    graph.add_edge("sql_generator", "sql_executor")
    graph.add_edge("sql_executor", "summarize")

    # 条件边:根据图表类型选择渲染方式
    graph.add_conditional_edges(
        "summarize",
        data_render_condition,
        {
            "data_render": "data_render",
            "data_render_apache": "data_render_apache"
        }
    )

    graph.add_edge("data_render", END)
    graph.add_edge("data_render_apache", END)

    return graph.compile()
```

**流程图可视化:**
```
schema_inspector
       ↓
[Neo4j启用?]
   ↓      ↓
table_relationship  (跳过)
       ↓      ↓
   sql_generator
       ↓
   sql_executor
       ↓
    summarize
       ↓
   [图表类型?]
   ↓         ↓
data_render  data_render_apache
   ↓         ↓
   END      END
```

### 3.4 Graph(图):组装完整流程

**编译与执行:**
```python
from langgraph.graph.state import CompiledStateGraph

# 创建图
graph = StateGraph(AgentState)
graph.add_node("step1", node1_func)
graph.add_node("step2", node2_func)
graph.add_edge("step1", "step2")
graph.set_entry_point("step1")
graph.add_edge("step2", END)

# 编译(优化执行路径)
compiled_graph: CompiledStateGraph = graph.compile()

# 执行
initial_state = AgentState(user_query="查询订单数据")
result = await compiled_graph.ainvoke(initial_state)
print(result["report_summary"])
```

**流式执行(实时获取中间结果):**
```python
async for chunk_dict in graph.astream(initial_state, stream_mode="updates"):
    node_name, node_output = next(iter(chunk_dict.items()))
    print(f"节点 {node_name} 输出: {node_output}")
```

**项目实战(`agent/text2sql/text2_sql_agent.py:55`):**
```python
async def run_agent(self, query: str, response=None, chat_id: str = None,
                    uuid_str: str = None, user_token=None) -> None:
    """运行 Text2SQL 智能体"""
    t02_answer_data = []
    t04_answer_data = {}
    current_step = None

    try:
        initial_state = AgentState(user_query=query, attempts=0, correct_attempts=0)
        graph: CompiledStateGraph = create_graph()

        # 流式执行
        async for chunk_dict in graph.astream(initial_state, stream_mode="updates"):
            langgraph_step, step_value = next(iter(chunk_dict.items()))

            # 处理步骤变更
            current_step = await self._handle_step_change(
                response, current_step, langgraph_step, t02_answer_data
            )

            # 处理具体步骤内容
            if step_value:
                await self._process_step_content(
                    response, langgraph_step, step_value,
                    t02_answer_data, t04_answer_data
                )
    except Exception as e:
        logger.error(f"Error in run_agent: {str(e)}")
```

**流式输出处理:**
```python
async def _handle_step_change(self, response, current_step, new_step, t02_answer_data):
    """处理步骤变更时的UI显示"""
    if self.show_thinking_process:
        if new_step != current_step:
            # 关闭前一个步骤的折叠框
            if current_step and current_step not in ["summarize", "data_render"]:
                await self._close_current_step(response, t02_answer_data)

            # 打开新步骤的折叠框
            if new_step not in ["summarize", "data_render"]:
                think_html = f"""<details style="color:gray;">
                             <summary>{new_step}...</summary>"""
                await self._send_response(response, think_html)
                t02_answer_data.append(think_html)

    return new_step, t02_answer_data
```

---

## 四、对比总结:传统方式 vs LangGraph

### 4.1 代码复杂度对比

**传统方式:**
```python
# 70 行代码,嵌套 5 层
async def traditional_pipeline(user_query):
    try:
        db_info = await get_db_info(user_query)
        if not db_info:
            return error_response("未找到表")

        try:
            sql = await generate_sql(user_query, db_info)
            if not sql:
                return error_response("SQL生成失败")

            try:
                result = await execute_sql(sql)
                if not result.success:
                    try:
                        corrected_sql = await correct_sql(sql, result.error)
                        result = await execute_sql(corrected_sql)
                        if not result.success:
                            return error_response("SQL执行失败")
                    except Exception as e:
                        return error_response(str(e))

                summary = await summarize(result.data)
                if needs_chart(user_query):
                    chart = await generate_chart(result.data)
                    return {"summary": summary, "chart": chart}
                return {"summary": summary}
            except Exception as e:
                return error_response(str(e))
        except Exception as e:
            return error_response(str(e))
    except Exception as e:
        return error_response(str(e))
```

**LangGraph 方式:**
```python
# 30 行代码,清晰扁平
def create_graph():
    graph = StateGraph(AgentState)

    graph.add_node("get_db_info", get_db_info)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("correct_sql", correct_sql)
    graph.add_node("summarize", summarize)
    graph.add_node("generate_chart", generate_chart)

    graph.set_entry_point("get_db_info")
    graph.add_edge("get_db_info", "generate_sql")
    graph.add_edge("generate_sql", "execute_sql")

    graph.add_conditional_edges(
        "execute_sql",
        lambda state: "correct_sql" if not state["execution_result"].success else "summarize"
    )
    graph.add_edge("correct_sql", "execute_sql")  # 重试

    graph.add_conditional_edges(
        "summarize",
        lambda state: "generate_chart" if needs_chart(state["user_query"]) else END
    )

    return graph.compile()
```

### 4.2 可维护性对比

| 对比维度 | 传统方式 | LangGraph |
|---------|---------|-----------|
| 流程可视化 | ❌ 需要画流程图 | ✅ 自动生成 Mermaid 图 |
| 单元测试 | ❌ 难以隔离测试 | ✅ 每个节点独立测试 |
| 错误定位 | ❌ 需要逐层调试 | ✅ 可以看到每个节点的状态变化 |
| 流程调整 | ❌ 需要修改多处 if-else | ✅ 只需调整边的连接 |
| 并行执行 | ❌ 需要手动管理 asyncio.gather | ✅ 自动识别可并行节点 |

### 4.3 适用场景

**使用传统方式的场景:**
- 流程简单(3步以内)
- 逻辑固定,不需要动态路由
- 性能要求极高(LangGraph 有少量开销)

**使用 LangGraph 的场景:**
- 多步骤流程(5步以上)
- 需要条件分支/循环
- 需要实时展示执行进度
- 团队协作(不同人负责不同节点)

---

## 五、项目架构总览

### 5.1 三个智能体对比

| 智能体 | 用途 | 技术栈 | 复杂度 |
|-------|------|--------|--------|
| CommonReact | 通用对话问答 | LangGraph + MCP Tools | ⭐⭐ |
| Text2SQL | 数据库问答 | LangGraph + BM25 + FAISS | ⭐⭐⭐⭐ |
| Excel | Excel文件分析 | LangGraph + DuckDB | ⭐⭐⭐ |

### 5.2 CommonReact Agent 流程

```
用户输入
   ↓
[需要调用工具?]
   ↓         ↓
调用MCP工具   直接回答
   ↓         ↓
   LLM 生成回答
   ↓
返回结果
```

### 5.3 Text2SQL Agent 流程

```
用户查询
   ↓
检索表结构(BM25+向量+重排)
   ↓
[启用Neo4j?]
   ↓      ↓
获取表关系  (跳过)
   ↓      ↓
生成SQL(Prompt Engineering)
   ↓
执行SQL
   ↓
LLM总结结果
   ↓
[需要图表?]
   ↓      ↓
生成图表  返回文本
   ↓      ↓
返回结果
```

---

## 六、实战练习:构建一个简单的 LangGraph 应用

### 6.1 需求:数学计算智能体

**功能:**
1. 接收用户的数学问题(如"计算 123 + 456")
2. 判断是否需要调用计算器工具
3. 如果需要,调用工具并返回结果
4. 否则直接用 LLM 回答

### 6.2 代码实现

```python
from typing import TypedDict, Optional, Literal
from langgraph.graph import StateGraph, END
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

# 1. 定义状态
class MathAgentState(TypedDict):
    user_query: str
    needs_calculator: bool
    calculation_result: Optional[float]
    final_answer: str

# 2. 定义节点
def classify_question(state: MathAgentState) -> MathAgentState:
    """判断是否需要计算器"""
    llm = ChatOpenAI()
    prompt = ChatPromptTemplate.from_template(
        "这个问题是否需要计算器?只回答'是'或'否':{question}"
    )
    chain = prompt | llm
    response = chain.invoke({"question": state["user_query"]})
    state["needs_calculator"] = "是" in response.content
    return state

def use_calculator(state: MathAgentState) -> MathAgentState:
    """调用计算器工具"""
    # 简化示例:用 eval 计算(生产环境应使用安全的计算库)
    try:
        result = eval(state["user_query"].replace("计算", ""))
        state["calculation_result"] = result
    except:
        state["calculation_result"] = None
    return state

def generate_answer(state: MathAgentState) -> MathAgentState:
    """生成最终答案"""
    if state.get("calculation_result") is not None:
        state["final_answer"] = f"计算结果是:{state['calculation_result']}"
    else:
        llm = ChatOpenAI()
        prompt = ChatPromptTemplate.from_template("请回答:{question}")
        chain = prompt | llm
        response = chain.invoke({"question": state["user_query"]})
        state["final_answer"] = response.content
    return state

# 3. 构建图
def create_math_agent():
    graph = StateGraph(MathAgentState)

    graph.add_node("classify", classify_question)
    graph.add_node("calculate", use_calculator)
    graph.add_node("answer", generate_answer)

    graph.set_entry_point("classify")

    graph.add_conditional_edges(
        "classify",
        lambda state: "calculate" if state["needs_calculator"] else "answer"
    )

    graph.add_edge("calculate", "answer")
    graph.add_edge("answer", END)

    return graph.compile()

# 4. 使用
agent = create_math_agent()
result = agent.invoke({"user_query": "计算 123 + 456"})
print(result["final_answer"])  # 输出: 计算结果是:579
```

---

## 七、本章总结

### 7.1 核心要点回顾

1. **LangChain 三大组件**: Prompt + LLM + OutputParser
2. **LCEL 链式调用**: 通过 `|` 组合多个组件
3. **LangGraph 四要素**: State, Node, Edge, Graph
4. **状态驱动**: 所有数据通过 State 传递,节点无副作用
5. **可视化优势**: 自动生成流程图,便于理解和调试

### 7.2 设计原则

1. **单一职责**: 每个节点只做一件事
2. **类型安全**: 使用 TypedDict 定义状态
3. **异常隔离**: 每个节点内部处理异常,不影响全局
4. **日志完整**: 记录每个节点的输入输出

### 7.3 下一章预告

下一章我们将实战 **CommonReact Agent**,学习如何:
- 集成 MCP(Model Context Protocol) 工具
- 实现多轮对话记忆
- 处理流式输出
- 任务取消机制

---

**完整文件清单:**
- `agent/common_react_agent.py` (362 行) - CommonReact Agent 实现
- `agent/text2sql/text2_sql_agent.py` (276 行) - Text2SQL Agent 主逻辑
- `agent/text2sql/state/agent_state.py` (68 行) - 状态定义
- `agent/text2sql/analysis/graph.py` (65 行) - 图构建
- `agent/text2sql/sql/generator.py` (104 行) - SQL生成节点
- `agent/text2sql/analysis/llm_summarizer.py` (132 行) - 总结节点
