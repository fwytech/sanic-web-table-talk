# 第8章 Text2SQL Agent 第二部分:Prompt 工程与 LangGraph 完整工作流

## 章节目标

1. 掌握 Text2SQL 的 Prompt Engineering 技巧,通过多层约束引导 LLM 生成高质量 SQL
2. 学会构建完整的 LangGraph 工作流,包括节点定义、边连接、条件路由
3. 理解流式输出的 UI 设计,使用 HTML details 标签实现思考过程折叠显示
4. 实践 SQL 执行与结果处理,掌握异常情况的优雅降级
5. 集成图表生成,支持 AntV MCP 与 Apache ECharts 双引擎渲染

## 一、SQL 生成:Prompt Engineering 的艺术

### 1.1 为什么 Prompt 设计很重要

**差的 Prompt:**

```python
prompt = "根据用户问题生成 SQL:{user_query}"

用户:"统计各省订单数"
LLM: "好的,这是 SQL:
SELECT * FROM orders WHERE province IS NOT NULL
"
# 问题:
# 1. 没有 GROUP BY(统计需要分组)
# 2. 没有 COUNT(统计需要计数)
# 3. 表名可能不对(orders? t_sales_orders?)
```

**好的 Prompt:**

```python
prompt = """
你是专业的 DBA,根据以下信息生成 SQL:

## 表结构
{db_schema}

## 用户问题
{user_query}

## 约束条件
1. 必须仅生成一条合法的 SQL 语句
2. 必须使用提供的表结构
3. 使用 GROUP BY、COUNT 等聚合函数
4. 输出格式:纯 JSON {"sql_query": "...", "chart_type": "..."}

## 当前时间
{current_time}
"""

用户:"统计各省订单数"
LLM: {
    "sql_query": "SELECT province, COUNT(*) as count FROM t_sales_orders GROUP BY province",
    "chart_type": "generate_bar_chart"
}
```

### 1.2 项目 Prompt 完整解析

**源码(`agent/text2sql/sql/generator.py:17`,精简版):**

```python
from langchain.prompts import ChatPromptTemplate
from datetime import datetime
import json

def sql_generate(state):
    llm = get_llm()

    prompt = ChatPromptTemplate.from_template(
        """
        你是一位专业的数据库管理员(DBA),任务是根据提供的数据库结构、表关系以及用户需求,生成优化的MYSQL SQL查询语句,并推荐合适的可视化图表。

        ## 任务
          - 根据用户问题生成一条优化的SQL语句。
          - 根据查询逻辑从**图表定义**中选择最合适的图表类型。

        ## 约束条件
         1. 你必须仅生成一条合法、可执行的SQL查询语句 —— 不得包含解释、Markdown、注释或额外文本。
         2. **必须直接且完整地使用所提供的表结构和表关系来生成SQL语句**。
         3. 你必须严格遵守数据类型、外键关系及表结构中定义的约束。
         4. 使用适当的SQL子句(JOIN、WHERE、GROUP BY、HAVING、ORDER BY、LIMIT等)以确保准确性和性能。
         5. 若问题涉及时序,请合理使用提供的"当前时间"上下文(例如用于相对日期计算)。
         6. 不得假设表结构中未明确定义的列或表。
         7. 如果用户问题模糊或者缺乏足够的信息以生成正确的查询,请返回:`NULL`
         8. 当用户明确要求查看明细数据且未指定具体数量时,应适当限制返回结果数量(如LIMIT 50)以提高查询性能,但如果用户指定了具体数量则按照用户要求执行
         9. 对于聚合查询或统计类查询,不应随意添加LIMIT子句

       ## 提供的信息
        - 表结构:{db_schema}
        - 表关系:{table_relationship}
        - 用户提问:{user_query}
        - 当前时间:{current_time}

        ## 图表定义
        - generate_area_chart: 面积图,展示连续变量下的数据趋势
        - generate_bar_chart: 条形图,用于横向比较不同类别的值
        - generate_column_chart: 柱状图,用于纵向比较不同类别的值
        - generate_line_chart: 折线图,展示数据随时间或连续变量的趋势
        - generate_pie_chart: 饼图,展示数据占比,以扇形表示各部分百分比
        - generate_table: 表格,以行列形式组织和呈现数据
        - generate_radar_chart: 雷达图,综合展示多维数据
        - generate_scatter_chart: 散点图,展示两个变量之间的关系
        ... (省略其他图表类型)

        ## 输出格式
        - 你**必须且只能**输出一个符合以下结构的 **纯 JSON 对象**,不得包含任何额外文本、注释、换行或 Markdown 格式:
        {{
            "sql_query": "生成的SQL语句字符串",
            "chart_type": "推荐的图表类型字符串,如 \"generate_bar_chart\""
        }}
    """
    )

    chain = prompt | llm

    try:
        response = chain.invoke({
            "db_schema": state["db_info"],
            "user_query": state["user_query"],
            "table_relationship": state.get("table_relationship", []),
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

        state["attempts"] += 1

        # 清理 JSON 格式(去除可能的 Markdown 包裹)
        clean_json_str = response.content.strip().removeprefix("```json").strip().removesuffix("```").strip()
        result = json.loads(clean_json_str)

        state["generated_sql"] = result["sql_query"]
        state["chart_type"] = "mcp-server-chart-" + result["chart_type"]  # MCP 工具前缀

    except Exception as e:
        logger.error(f"Error in generating: {e}")
        state["generated_sql"] = "No SQL query generated"

    return state
```

### 1.3 Prompt 设计要点

**1. 角色定位 + 任务明确**

```
你是一位专业的数据库管理员(DBA)
任务是生成优化的 MYSQL SQL查询语句
```

**作用:** 让 LLM 进入"DBA 模式",提高专业性

**2. 多层约束(9条规则)**

```
1. 仅生成一条 SQL
2. 必须使用提供的表结构
3. 遵守数据类型约束
4. 使用适当的 SQL 子句
...
```

**作用:** 约束 LLM 行为,减少幻觉

**3. 上下文注入**

```
- 表结构:{db_schema}
- 表关系:{table_relationship}
- 当前时间:{current_time}
```

**作用:** 提供必要信息,避免 LLM 编造

**4. 图表类型推荐**

```
## 图表定义
- generate_bar_chart: 条形图,用于横向比较
- generate_pie_chart: 饼图,展示数据占比
...
```

**作用:** 让 LLM 同时推荐可视化方式

**5. 强制 JSON 输出**

```
## 输出格式
你**必须且只能**输出纯 JSON 对象:
{
    "sql_query": "...",
    "chart_type": "..."
}
```

**作用:** 结构化输出,便于解析

### 1.4 常见 SQL 生成场景

**场景1:简单统计**

```
用户:"统计各省订单数"
表结构:t_sales_orders (order_id, customer_id, order_date, province, total_amount)

生成 SQL:
SELECT province, COUNT(*) as count
FROM t_sales_orders
GROUP BY province
ORDER BY count DESC

推荐图表: generate_bar_chart (条形图)
```

**场景2:时间范围查询**

```
用户:"查询最近一周的订单"
当前时间:2024-01-15 10:30:00

生成 SQL:
SELECT *
FROM t_sales_orders
WHERE order_date >= DATE_SUB('2024-01-15', INTERVAL 7 DAY)
ORDER BY order_date DESC
LIMIT 50

推荐图表: generate_table (表格)
```

**场景3:多表关联**

```
用户:"查询各客户的订单总金额"
表结构:
- t_sales_orders (order_id, customer_id, total_amount)
- t_customers (customer_id, customer_name, city)
表关系:t_sales_orders.customer_id = t_customers.customer_id

生成 SQL:
SELECT c.customer_name, SUM(o.total_amount) as total
FROM t_sales_orders o
JOIN t_customers c ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY total DESC

推荐图表: generate_column_chart (柱状图)
```

---

## 二、LangGraph 工作流完整构建

### 2.1 状态定义

**AgentState 完整字段(`agent/text2sql/state/agent_state.py:48`):**

```python
from typing import TypedDict, Optional, Dict, List, Any
from pydantic import BaseModel, Field

class ExecutionResult(BaseModel):
    """SQL 执行结果"""
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    error: Optional[str] = None

class AgentState(TypedDict):
    """Text2SQL Agent 状态"""
    user_query: str  # 用户问题
    db_info: Optional[Dict]  # 数据库表结构
    table_relationship: Optional[List[Dict[str, Any]]]  # 表关系(Neo4j)
    generated_sql: Optional[str]  # 生成的 SQL
    execution_result: Optional[ExecutionResult]  # SQL 执行结果
    report_summary: Optional[str]  # LLM 总结
    attempts: int = 0  # 尝试次数
    chart_url: Optional[str]  # AntV 图表 URL
    chart_type: Optional[str]  # 图表类型
    apache_chart_data: Optional[Dict[str, Any]]  # Apache ECharts 数据
```

**字段用途说明:**

| 字段 | 用途 | 更新节点 |
|-----|------|---------|
| `user_query` | 用户原始问题 | 初始化 |
| `db_info` | 检索到的表结构 | `schema_inspector` |
| `table_relationship` | 表关系(可选) | `table_relationship` |
| `generated_sql` | 生成的 SQL | `sql_generator` |
| `execution_result` | 执行结果 | `sql_executor` |
| `report_summary` | 数据分析报告 | `summarize` |
| `chart_url` | AntV 图表链接 | `data_render` |
| `apache_chart_data` | ECharts 配置 | `data_render_apache` |

### 2.2 节点定义

**完整节点列表(`agent/text2sql/analysis/graph.py:31`):**

```python
from langgraph.graph import StateGraph, END

def create_graph():
    graph = StateGraph(AgentState)
    db_service = DatabaseService()

    # 添加所有节点
    graph.add_node("schema_inspector", db_service.get_table_schema)  # 表结构检索
    graph.add_node("table_relationship", get_table_relationship)  # 表关系查询(Neo4j)
    graph.add_node("sql_generator", sql_generate)  # SQL 生成
    graph.add_node("sql_executor", db_service.execute_sql)  # SQL 执行
    graph.add_node("summarize", summarize)  # LLM 总结
    graph.add_node("data_render", data_render_ant)  # AntV 图表渲染
    graph.add_node("data_render_apache", data_render_apache)  # Apache 图表渲染

    # ... 边连接(见下文)

    return graph.compile()
```

### 2.3 边连接与条件路由

**完整边定义:**

```python
# 1. 设置入口点
graph.set_entry_point("schema_inspector")

# 2. 条件边:是否启用 Neo4j
neo4j_enabled = os.getenv("NEO4J_ENABLED", "false").lower() == "true"
if neo4j_enabled:
    graph.add_node("table_relationship", get_table_relationship)
    graph.add_edge("schema_inspector", "table_relationship")
    graph.add_edge("table_relationship", "sql_generator")
else:
    graph.add_edge("schema_inspector", "sql_generator")  # 跳过表关系查询

# 3. 固定边
graph.add_edge("sql_generator", "sql_executor")
graph.add_edge("sql_executor", "summarize")

# 4. 条件边:根据图表类型选择渲染方式
def data_render_condition(state: AgentState) -> str:
    """根据 chart_type 判断使用哪种图表渲染"""
    chart_type = state.get("chart_type")
    if not chart_type or chart_type.lower() in ["mcp-server-chart-generate_table"]:
        return "data_render_apache"  # 表格使用 Apache ECharts
    return "data_render"  # 其他图表使用 AntV MCP

graph.add_conditional_edges(
    "summarize",
    data_render_condition,
    {
        "data_render": "data_render",
        "data_render_apache": "data_render_apache"
    }
)

# 5. 结束边
graph.add_edge("data_render", END)
graph.add_edge("data_render_apache", END)
```

**流程图可视化:**

```
        START
          │
          ▼
   schema_inspector
          │
     [Neo4j启用?]
       ┌──┴──┐
       ▼     ▼
table_relationship  (跳过)
       │     │
       └──┬──┘
          ▼
    sql_generator
          │
          ▼
    sql_executor
          │
          ▼
      summarize
          │
     [图表类型?]
       ┌──┴──┐
       ▼     ▼
  data_render  data_render_apache
       │     │
       └──┬──┘
          ▼
         END
```

### 2.4 条件路由函数详解

**路由函数(`agent/text2sql/analysis/graph.py:18`):**

```python
def data_render_condition(state: AgentState) -> str:
    """
    根据 chart_type 判断使用哪种图表渲染方式
    """
    chart_type = state.get("chart_type")
    logger.info(f"chart_type: {chart_type}")

    # 表格类型使用 Apache ECharts
    if not chart_type or chart_type.lower() in ["mcp-server-chart-generate_table"]:
        return "data_render_apache"

    # 其他图表使用 AntV MCP
    return "data_render"
```

**为什么需要两种渲染方式:**

| 方式 | 引擎 | 适用场景 | 优势 |
|-----|------|---------|------|
| `data_render` | AntV MCP | 柱状图、饼图、折线图等 | 美观、交互性强 |
| `data_render_apache` | Apache ECharts | 表格、复杂图表 | 兼容性好、稳定 |

---

## 三、流式输出与 UI 设计

### 3.1 思考过程折叠显示

**用户体验设计:**

```html
<details style="color:gray;background-color:#f8f8f8;">
  <summary>schema_inspector...</summary>
  共检索4张表: t_sales_orders(销售订单主表)、t_customers(客户信息表)...
</details>

<details>
  <summary>sql_generator...</summary>
  SELECT province, COUNT(*) FROM t_sales_orders GROUP BY province
</details>

<details>
  <summary>sql_executor...</summary>
  执行sql语句成功
</details>

## 数据分析
北京订单数最多(120单),其次是上海(95单)...

[柱状图]
```

**为什么这样设计:**
1. **思考过程可折叠**: 用户可选择查看细节
2. **最终结果直接展示**: 重要信息不隐藏
3. **灰色背景区分**: 思考过程与结果视觉分离

### 3.2 流式处理步骤变更

**完整实现(`agent/text2sql/text2_sql_agent.py:109`):**

```python
async def _handle_step_change(
    self,
    response,
    current_step: Optional[str],
    new_step: str,
    t02_answer_data: list,
) -> tuple:
    """处理步骤变更"""
    if self.show_thinking_process:  # 环境变量控制是否显示
        if new_step != current_step:
            # 关闭前一个步骤的 details 标签
            if current_step and current_step not in ["summarize", "data_render", "data_render_apache"]:
                await self._close_current_step(response, t02_answer_data)

            # 打开新步骤的 details 标签
            if new_step not in ["summarize", "data_render", "data_render_apache"]:
                think_html = f"""<details style="color:gray;background-color: #f8f8f8;padding: 2px;border-radius: 6px;margin-top:5px;">
                             <summary>{new_step}...</summary>"""
                await self._send_response(response, think_html)
                t02_answer_data.append(think_html)

    return new_step, t02_answer_data

async def _close_current_step(self, response, t02_answer_data: list) -> None:
    """关闭当前步骤的 details 标签"""
    if self.show_thinking_process:
        close_tag = "</details>\n\n"
        await self._send_response(response, close_tag)
        t02_answer_data.append(close_tag)
```

**关键逻辑:**
1. **步骤变更检测**: `new_step != current_step`
2. **选择性隐藏**: `summarize` 和 `data_render` 不包裹在 details 中
3. **环境变量控制**: `SHOW_THINKING_PROCESS=true/false`

### 3.3 步骤内容处理

**内容映射(`agent/text2sql/text2_sql_agent.py:150`):**

```python
async def _process_step_content(
    self,
    response,
    step_name: str,
    step_value: Dict[str, Any],
    t02_answer_data: list,
    t04_answer_data: Dict[str, Any],
) -> None:
    """处理各个步骤的内容"""

    # 内容格式化映射
    content_map = {
        "schema_inspector": lambda: self._format_db_info(step_value["db_info"]),
        "sql_generator": lambda: step_value["generated_sql"],
        "sql_executor": lambda: "执行sql语句成功" if step_value["execution_result"].success else "执行sql语句失败",
        "summarize": lambda: step_value["report_summary"],
        "data_render": lambda: step_value["chart_url"],
        "data_render_apache": lambda: step_value["apache_chart_data"],
    }

    if step_name in content_map:
        content = content_map[step_name]()

        # 判断数据类型
        if step_name == "data_render_apache":
            data_type = DataTypeEnum.BUS_DATA.value[0]  # t04
        else:
            data_type = DataTypeEnum.ANSWER.value[0]  # t02

        # 根据环境变量决定是否发送
        should_send = self.show_thinking_process or step_name in ["summarize", "data_render", "data_render_apache"]

        if should_send:
            await self._send_response(response=response, content=content, data_type=data_type)

            # 保存到数据列表
            if data_type == DataTypeEnum.ANSWER.value[0]:
                t02_answer_data.append(content)
            elif step_name in ["data_render", "data_render_apache"]:
                t04_answer_data.clear()
                t04_answer_data.update({"data": content, "dataType": data_type})
```

**格式化示例:**

```python
@staticmethod
def _format_db_info(db_info: Dict[str, Any]) -> str:
    """格式化数据库信息"""
    if not db_info:
        return "共检索0张表."

    table_descriptions = []
    for table_name, table_info in db_info.items():
        table_comment = table_info.get("table_comment", "")
        if table_comment:
            table_descriptions.append(f"{table_name}({table_comment})")
        else:
            table_descriptions.append(table_name)

    tables_str = "、".join(table_descriptions)
    return f"共检索{len(db_info)}张表: {tables_str}."
```

**输出示例:**

```
共检索4张表: t_sales_orders(销售订单主表)、t_customers(客户信息表)、t_order_details(订单明细表)、t_products(产品信息表).
```

---

## 四、数据总结:LLM 驱动的智能分析

### 4.1 总结节点 Prompt 设计

**完整 Prompt(`agent/text2sql/analysis/llm_summarizer.py:17`):**

```python
from langchain.prompts import ChatPromptTemplate

def summarize(state: AgentState):
    llm = get_llm()

    prompt = ChatPromptTemplate.from_template(
        """
        # Role: 数据趋势分析师

        ## Profile
        - language: 简体中文
        - description: 从复杂数据中提取关键趋势的资深分析师
        - expertise: 时间序列分析、结构洞察、异常检测、模式识别

        ## INPUT_DATA
          {data_result}

        ### QUESTION ###
          User's Question: {user_query}
          Current Time: {current_time}

        ## Skills
        1. 数据分析核心技能
           - 趋势识别:判断时间序列的变动方向、拐点、周期性
           - 结构洞察:识别分布特征、集中度、异常值
           - 模式归纳:提炼品类/用户/行为差异信号
           - 异常检测:发现偏离常规的异常数值

        2. 辅助分析技能
           - 指标构建:提取客单价、订单密度、转化率等关键指标
           - 驱动分析:定位主导整体表现的核心因素
           - 业务推断:结合常识推导潜在动因或风险

        ## Rules
        1. 基本原则:
           - 数据驱动:所有结论必须基于实际数据
           - 逻辑闭环:分析过程与结论之间需具备因果关系
           - 精炼表达:语言简洁、重点突出

        2. 限制条件:
           - 语言限制:仅使用简体中文
           - 长度限制:总输出控制在300字以内,关键发现2-3项
           - 输出限制:仅输出结构化分析内容

        ## Workflows
        - 步骤 1: 识别数据结构(时间序列/截面数据)
        - 步骤 2: 提取关键指标与核心趋势
        - 步骤 3: 归纳驱动因素与潜在风险

        ## OutputFormat
        - format: markdown
        - structure: "整体概括 - 关键发现"
        - style: 简洁、专业、数据驱动
        - special_requirements: 不使用代码块,禁用HTML标签

        ## 示例
        示例1:
          ## 🧩 数据分析
          当前销售数据呈现明显的集中趋势,前10名商品中饮料类占据主导。

          ## **📌 关键发现**
          - 🔍 销售额环比增长6.2%,低于前两周平均12.5%,存在增速放缓迹象
          - 📈 订单密度下降5.3%,表明用户活跃度可能减弱
          - 📦 客单价提升11%,主要由高单价商品销量增加驱动

        ## Initialization
        作为数据趋势分析师,你必须遵守上述Rules,按照Workflows执行任务,并按照[输出格式]输出。
        """
    )

    chain = prompt | llm

    try:
        response = chain.invoke({
            "data_result": state["execution_result"].data,
            "user_query": state["user_query"],
            "current_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        state["report_summary"] = response.content

    except Exception as e:
        logger.error(f"Error in Summarizer: {e}")
        state["report_summary"] = "No summary provided"

    return state
```

### 4.2 总结示例

**输入数据:**

```python
data_result = [
    {"province": "北京", "count": 120},
    {"province": "上海", "count": 95},
    {"province": "广东", "count": 85},
    {"province": "浙江", "count": 62},
    {"province": "江苏", "count": 58}
]
user_query = "统计各省订单数"
```

**LLM 输出:**

```markdown
## 🧩 数据分析
从各省订单数据来看,呈现明显的集中趋势,北京、上海、广东三地占据订单总量的60%以上。

## **📌 关键发现**
- 🔍 北京订单数最多(120单),领先上海25单,显示华北市场活跃度最高
- 📈 前三名省份订单数均超过80单,形成第一梯队,与其他省份拉开明显差距
- 📦 长三角地区(上海、浙江、江苏)合计订单数215单,显示区域集群效应明显
```

### 4.3 设计要点

1. **角色明确**: "数据趋势分析师"  → 专业分析视角
2. **输入结构化**: 明确提供 data_result、user_query、current_time
3. **技能列表**: 告诉 LLM 应该从哪些角度分析
4. **输出约束**: 300字以内、2-3项关键发现、Markdown 格式
5. **示例引导**: 提供标准格式示例

---

## 五、图表生成:双引擎渲染策略

### 5.1 AntV MCP 图表渲染

**节点实现(概念版):**

```python
async def data_render_ant(state: AgentState) -> AgentState:
    """
    使用 AntV MCP 服务生成图表
    """
    chart_type = state.get("chart_type")
    execution_result = state.get("execution_result")

    if not execution_result or not execution_result.success:
        state["chart_url"] = None
        return state

    try:
        # 调用 MCP 工具
        mcp_client = MultiServerMCPClient(...)
        tools = await mcp_client.get_tools()

        # 找到对应的图表生成工具
        chart_tool = next(t for t in tools if t.name == chart_type)

        # 调用工具生成图表
        chart_result = await chart_tool.invoke({
            "data": execution_result.data,
            "xField": "province",
            "yField": "count"
        })

        state["chart_url"] = chart_result.url

    except Exception as e:
        logger.error(f"AntV 图表生成失败: {e}")
        state["chart_url"] = None

    return state
```

### 5.2 Apache ECharts 图表渲染

**节点实现(`agent/text2sql/analysis/data_render_apache.py`,概念版):**

```python
def data_render_apache(state: AgentState) -> AgentState:
    """
    使用 Apache ECharts 渲染图表数据
    """
    execution_result = state.get("execution_result")
    chart_type = state.get("chart_type")

    if not execution_result or not execution_result.success:
        return state

    try:
        data = execution_result.data

        # 根据图表类型构建 ECharts 配置
        if "table" in chart_type.lower():
            # 表格数据
            chart_config = {
                "chart_type": "表格",
                "template_code": "temp01",
                "data": data,
                "note": "数据来源: xxx数据库"
            }
        elif "bar" in chart_type.lower():
            # 柱状图
            chart_config = {
                "chart_type": "柱状图",
                "template_code": "temp03",
                "data": [["类别", "数值"]] + [[row["province"], row["count"]] for row in data],
                "note": "数据来源: xxx数据库"
            }
        elif "pie" in chart_type.lower():
            # 饼图
            chart_config = {
                "chart_type": "饼图",
                "template_code": "temp02",
                "data": [{"name": row["province"], "value": row["count"], "percent": False} for row in data],
                "note": "数据来源: xxx数据库"
            }

        state["apache_chart_data"] = chart_config

    except Exception as e:
        logger.error(f"Apache 图表生成失败: {e}")
        state["apache_chart_data"] = {}

    return state
```

### 5.3 双引擎对比

| 对比维度 | AntV MCP | Apache ECharts |
|---------|----------|----------------|
| 调用方式 | MCP 远程服务 | 本地 Python 构建 |
| 图表样式 | 美观、现代化 | 传统、稳定 |
| 适用场景 | 柱状图、饼图、折线图 | 表格、复杂图表 |
| 依赖 | 需要 MCP 服务可用 | 无外部依赖 |
| 响应时间 | 稍慢(网络请求) | 快速 |

---

## 六、完整 Agent 执行流程

### 6.1 run_agent 主函数

**源码(`agent/text2sql/text2_sql_agent.py:28`,精简版):**

```python
async def run_agent(
    self, query: str, response=None, chat_id: str = None,
    uuid_str: str = None, user_token=None
) -> None:
    """运行 Text2SQL 智能体"""
    t02_answer_data = []
    t04_answer_data = {}
    current_step = None

    try:
        # 1. 初始化状态
        initial_state = AgentState(user_query=query, attempts=0)

        # 2. 创建图
        graph: CompiledStateGraph = create_graph()

        # 3. 任务取消标志
        user_dict = await decode_jwt_token(user_token)
        task_id = user_dict["id"]
        task_context = {"cancelled": False}
        self.running_tasks[task_id] = task_context

        # 4. 流式执行
        async for chunk_dict in graph.astream(initial_state, stream_mode="updates"):

            # 检查是否已取消
            if self.running_tasks[task_id]["cancelled"]:
                await response.write(
                    self._create_response("\n> 这条消息已停止", "info")
                )
                break

            # 解析步骤名和输出
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

        # 5. 关闭最后的 details 标签
        if self.show_thinking_process:
            if current_step and current_step not in ["summarize", "data_render"]:
                await self._close_current_step(response, t02_answer_data)

        # 6. 保存问答记录
        if not self.running_tasks[task_id]["cancelled"]:
            await add_user_record(
                uuid_str, chat_id, query,
                t02_answer_data, t04_answer_data,
                DiFyAppEnum.DATABASE_QA.value[0],
                user_token, {}
            )

    except Exception as e:
        logger.error(f"Error in run_agent: {str(e)}")
        await self._send_response(response, f"处理过程中发生错误: {str(e)}", "error")
```

### 6.2 执行流程时序图

```
用户请求
   │
   ▼
run_agent() 初始化
   │
   ├─ 创建初始状态
   ├─ 创建 Graph
   └─ 设置取消标志
   │
   ▼
graph.astream() 流式执行
   │
   ├─ schema_inspector → 检索表结构
   │   └─ SSE 输出: "共检索4张表..."
   │
   ├─ [Neo4j 启用?]
   │   └─ table_relationship → 查询表关系
   │       └─ SSE 输出: {...}
   │
   ├─ sql_generator → 生成 SQL
   │   └─ SSE 输出: "SELECT province, COUNT(*) ..."
   │
   ├─ sql_executor → 执行 SQL
   │   └─ SSE 输出: "执行sql语句成功"
   │
   ├─ summarize → LLM 总结
   │   └─ SSE 输出: "## 数据分析\n北京订单最多..."
   │
   ├─ [图表类型?]
   │   ├─ data_render → AntV 图表
   │   │   └─ SSE 输出: chart_url
   │   └─ data_render_apache → ECharts 图表
   │       └─ SSE 输出: chart_data (t04)
   │
   ▼
保存问答记录
   │
   ▼
返回前端
```

---

## 七、本章总结

### 7.1 核心要点回顾

1. **Prompt Engineering**: 多层约束 + 结构化输出引导 LLM 生成高质量 SQL
2. **LangGraph 工作流**: 6个节点 + 条件路由实现完整的 Text2SQL 流程
3. **流式输出 UI**: HTML details 标签折叠思考过程,提升用户体验
4. **LLM 总结**: 专业分析师角色 + 示例引导生成数据分析报告
5. **双引擎图表**: AntV MCP(美观) + Apache ECharts(稳定)

### 7.2 Text2SQL 完整技术栈

```
┌──────────────────────────────────────┐
│         Text2SQL Agent               │
├──────────────────────────────────────┤
│ 表结构检索                            │
│  - BM25 关键词匹配                    │
│  - FAISS 向量检索                     │
│  - RRF 融合                           │
│  - DashScope Rerank 重排               │
├──────────────────────────────────────┤
│ SQL 生成                              │
│  - Prompt Engineering                 │
│  - LangChain ChatPromptTemplate       │
│  - 图表类型推荐                        │
├──────────────────────────────────────┤
│ 工作流编排                            │
│  - LangGraph StateGraph               │
│  - 条件路由(Neo4j/图表选择)            │
│  - 流式输出(SSE)                       │
├──────────────────────────────────────┤
│ 数据分析                              │
│  - LLM 驱动的智能总结                  │
│  - Markdown 格式化输出                 │
├──────────────────────────────────────┤
│ 图表渲染                              │
│  - AntV MCP(远程服务)                  │
│  - Apache ECharts(本地构建)            │
└──────────────────────────────────────┘
```

### 7.3 性能优化建议

1. **缓存 SQL 结果**: 相同查询缓存 5 分钟
2. **限制返回行数**: 明细查询默认 LIMIT 50
3. **异步并行执行**: 表结构检索与表关系查询并行
4. **降级策略**: MCP 服务不可用时使用 Apache 兜底

### 7.4 第二部分总结

第二部分(共4章)完整覆盖了 LangChain/LangGraph 智能体基础:

- **第5章**: LangChain/LangGraph 核心概念
- **第6章**: CommonReact Agent - MCP 工具集成
- **第7章**: Text2SQL Agent - BM25 + 向量混合检索
- **第8章**: Text2SQL Agent - Prompt 工程与 LangGraph 工作流

**下一部分预告:**

第三部分将学习 **高级智能体与部署实战**,包括:
- Excel Agent 实现(DuckDB + LangGraph)
- 前端集成(Vue3 + SSE)
- Docker 容器化部署
- 性能监控与日志管理

---

**完整文件清单:**
- `agent/text2sql/text2_sql_agent.py` (276 行) - Agent 主逻辑
- `agent/text2sql/sql/generator.py` (104 行) - SQL 生成节点
- `agent/text2sql/analysis/llm_summarizer.py` (132 行) - 总结节点
- `agent/text2sql/analysis/graph.py` (65 行) - 图构建
- `agent/text2sql/analysis/data_render_antv.py` - AntV 渲染节点
- `agent/text2sql/analysis/data_render_apache.py` - Apache 渲染节点
