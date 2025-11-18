# LangGraph + MCP + Sanic 构建智能问数系统
[![English](https://img.shields.io/badge/English-Click-yellow)](README-en.md)

🌟 **项目简介**

一个基于 **LangGraph + MCP + Sanic** 的轻量级、全链路智能问数系统，支持快速二次开发。

**核心特性：多智能体架构 + SSE流式响应 + Text2SQL**

本项目基于 **LangChain/LangGraph、MCP、Neo4j、Ollama、Sanic 和 Text2SQL** 📊 等技术栈，采用
**Vue3 + TypeScript + Vite** 打造现代化前端界面。支持通过 **ECharts/AntV(mcp-server-chart)** 📈 实现数据可视化问答，具备 **CSV/Excel** 文件 📂 表格智能分析能力，并可对接第三方 **RAG** 检索系统 🌐 支持通用知识问答。

作为轻量级的智能体应用开发框架，本项目 🛠️ 支持快速迭代与扩展，助力企业级 AI 应用快速落地。🚀



## 架构方案
![image](./docs/docs/images/app-01.png)

## 🎉 **核心特性**

### 🤖 智能体架构
- **LangGraph 状态图编排**：基于 StateGraph 实现复杂的多步骤智能体工作流
- **MCP 协议集成**：支持 MCP Server Chart 等标准化工具调用
- **多 Agent 协同**：CommonReactAgent、Text2SQLAgent、ExcelAgent 等专业智能体

### 🔧 技术栈
- **后端框架**：Sanic (异步高性能) + SQLAlchemy 2.0 + MySQL
- **智能体框架**：LangChain/LangGraph + MCP
- **大模型支持**：Ollama (Qwen2.5/DeepSeek-R1) + Dify 对接
- **前端技术**：Vue 3 + TypeScript + Vite + Pinia + Naive UI
- **数据可视化**：ECharts + AntV MCP Server Chart

### 📊 核心功能
- **Text2SQL 智能问数**：BM25 + 向量混合检索 + Neo4j 语义图谱增强
- **Excel/CSV 分析**：Pandas + DuckDB 实现表格智能问答
- **SSE 流式响应**：TransformStream 管道处理，打造 ChatGPT 级体验
- **Docker 一键部署**：包含 MySQL、MinIO、Neo4j 等完整技术栈

### 🚀 项目优势
- **轻量级全链路**：覆盖前后端、智能体、部署的完整解决方案
- **易于二次开发**：清晰的代码结构 + 完整的 16 章教程文档
- **生产级实践**：JWT 认证、统一异常处理、日志系统

## 案例展示

<table>
<tbody>
<tr>
<td><img src="./docs/docs/images/chat-05.png" alt="" style="width:400px;max-height:640px; min-height: 200px"></td>
<td><img src="./docs/docs/images/chat-06.png" alt="" style="width:400px;max-height:640px; min-height: 200px"></td>
</tr>
<tr>
<td><img src="./docs/docs/images/chat-07.png" alt="" style="width:400px;max-height:640px; min-height: 200px"></td>
<td><img src="./docs/docs/images/chat-09.png" alt="" style="width:400px;max-height:640px; min-height: 200px"></td>
</tr>
</tbody>
</table>

<table>
<tbody>
<tr>
<td>

<video src="https://github.com/user-attachments/assets/0186b574-8267-4e99-8b9d-77eaee4fd02e" controls="controls" muted="muted" class="d-block rounded-bottom-2 border-top width-fit" style="max-height:640px; min-height: 200px">
</video>

<td>

<video src="https://github.com/user-attachments/assets/5037ba3b-4480-4be0-8d19-74a18cfd1225" controls="controls" muted="muted" class="d-block rounded-bottom-2 border-top width-fit" style="max-height:640px; min-height: 200px">
</video>

</td>
</tr>
<tr>
<td>
<video src="https://github.com/user-attachments/assets/8dad64a6-8eee-4d68-a0f4-f30e92f52594" controls="controls" muted="muted" class="d-block rounded-bottom-2 border-top width-fit" style="max-height:640px; min-height: 200px">
</video>
</td>
<td>

<video src="https://github.com/user-attachments/assets/228d5710-12d8-4ae4-bad1-65135813745f" controls="controls" muted="muted" class="d-block rounded-bottom-2 border-top width-fit" style="max-height:640px; min-height: 200px">
</video>

</td>
</tr>
</tbody>
</table>

## 📚 完整教程文档

本项目提供完整的 **16 章系列教程**，覆盖从后端架构到前端开发的全栈技术：

### 第一部分：基础架构篇 (第 1-4 章)
- 第 1 章：为什么选 Sanic - 从零理解 Python 异步 Web 框架的核心机制
- 第 2 章：UV 包管理器极速搭建项目骨架
- 第 3 章：SQLAlchemy 2.0 + MySQL 双引擎数据层设计哲学
- 第 4 章：JWT 无状态认证 + 统一异常处理的工程化实践

### 第二部分：LangChain 与 LangGraph 智能体基础 (第 5-8 章)
- 第 5 章：LangChain 与 LangGraph 核心概念 - 从传统函数到状态图的范式转变
- 第 6 章：CommonReactAgent 实战 - MCP 工具集成与多轮对话记忆
- 第 7 章：Text2SQLAgent 第一部分 - BM25 + 向量混合检索与智能表结构匹配
- 第 8 章：Text2SQLAgent 第二部分 - Prompt 工程与 LangGraph 完整工作流

### 第三部分：智能体应用篇 (第 9-12 章)
- 第 9 章：ExcelAgent 实战 - Pandas + DuckDB 实现表格问答
- 第 10 章：前端集成与 SSE 流式响应 - 打造 ChatGPT 级用户体验
- 第 11 章：可选集成 Neo4j 与 MinIO - 按需扩展的架构设计
- 第 12 章：Docker 容器化部署 - 一键启动生产级技术栈

### 第四部分：前端开发篇 (第 13-16 章)
- 第 13 章：Vue3 + Vite 前端框架概览 - 基于 chatgpt-vue3-light-mvp 的轻量级实现
- 第 14 章：项目配置与构建优化 - 从开发到生产的完整流程
- 第 15 章：核心 UI 组件实现 - 打造 ChatGPT 级交互体验
- 第 16 章：前后端集成实战 - 完整数据流与状态管理

> 📖 所有教程位于 `Tutorial/` 目录，包含完整代码示例、架构图和思考题。

## 🌹 支持

如果你喜欢这个项目或发现有用，可以点右上角 [`Star`](https://github.com/apconw/sanic-web) 支持一下，你的支持是我们不断改进的动力，感谢！ ^_^

## 💬 技术支持

### 微信公众号文章
- 想了解更多？欢迎关注微信公众号获取最新技术文章：

<table>
<tbody>
<tr>
<td><img src="/docs/docs/images/ocr.png" alt="" style="width:60px;height:40px;"></td>
<td><a href="https://mp.weixin.qq.com/s/kxzDs0chEqHYBYE_u8TZZw">大模型如何读懂任何格式文件并自动生成报告？LangGraph + MCP 实战解析</a></td>
</tr>
<tr>
<td><img src="/docs/docs/images/antv-chart.png" alt="" style="width:60px;height:40px;"></td>
<td><a href="https://mp.weixin.qq.com/s/8KmZaIEnCZlHFp_1oyknMA">用 AntV MCP Server Chart 赋能大模型 —— 从零构建可视化智能体，图表生成效率飙升！</a></td>
</tr>
<tr>
<td><img src="/docs/docs/images/eno4j.png" alt="" style="width:60px;height:40px;"></td>
<td><a href="https://mp.weixin.qq.com/s/XOdAeua2UyPxASM1CeXPmg">Neo4j构建语义图谱，大模型秒懂表关系，Text2SQL准确率狂飙300%！告别瞎猜！</a></td>
</tr>
<tr>
<td><img src="/docs/docs/images/text2sql.png" alt="" style="width:60px;height:40px;"></td>
<td><a href="https://mp.weixin.qq.com/s/sjCJNbdoNAfFOECWUKfElw">用 BM25 + 中文分词实现 Text2SQL 表过滤 —— 让大模型只看"相关表"，准确率飙升！</a></td>
</tr>
</tbody>
</table>

## ⭐ Star History
[![Star History Chart](https://api.star-history.com/svg?repos=apconw/sanic-web&type=Date)](https://star-history.com/#apconw/sanic-web&Date)

## 📖 相关资源

### 开源框架
- **前端框架**：[chatgpt-vue3-light-mvp](https://github.com/pdsuwwz/chatgpt-vue3-light-mvp) - ChatGPT 风格的 Vue3 轻量级前端
- **Dify 工作流**：[dify-for-dsl](https://github.com/wwwzhouhui/dify-for-dsl) - Dify 工作流 DSL 清单合集

### 技术文档
- **LangChain 官方文档**：https://python.langchain.com/
- **LangGraph 官方文档**：https://langchain-ai.github.io/langgraph/
- **MCP 协议规范**：https://modelcontextprotocol.io/
- **Sanic 框架文档**：https://sanic.dev/

## License

[MIT](./LICENSE) License | Copyright © 2024-PRESENT [AiAdventurer](https://github.com/apconw)

---

<div align="center">

**如果这个项目对你有帮助，请点个 ⭐ Star 支持一下！**

</div>

