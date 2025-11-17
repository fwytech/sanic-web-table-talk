# sanic-web

基于 Vue3 + Vite5 + TypeScript + Naive UI 的前端项目

## 环境要求

- Node.js >= 18
- pnpm (推荐)

## 安装依赖

```bash
pnpm i
```

## 本地开发

```bash
pnpm dev
```

## 构建生产版本

```bash
pnpm build
```

## 代码规范检查

```bash
# ESLint 检查
pnpm lint

# 自动修复 ESLint 问题
pnpm lint:fix

# Stylelint 检查
pnpm stylelint

# 自动修复样式问题
pnpm stylelint:fix
```

## API 配置

复制 `.env.template` 为 `.env`，并配置相关 API 密钥：

```bash
cp .env.template .env
```

编辑 `.env` 文件，填入你的 API 密钥：

```env
# 讯飞星火大模型 API 配置
VITE_SPARK_KEY=你的APIKey:你的APISecret

# SiliconFlow API 配置
VITE_SILICONFLOW_KEY=sk-你的密钥
```

## 大模型集成

本项目支持集成以下大模型：

- **讯飞星火大模型**: 需要配置 `VITE_SPARK_KEY`
- **SiliconFlow**: 需要配置 `VITE_SILICONFLOW_KEY`

## 功能特性

- 📊 表格数据问答
- 📈 图表可视化
- 💬 智能对话
- 📁 文件上传和处理
- 🔒 用户认证

## 技术栈

- **前端框架**: Vue 3
- **构建工具**: Vite 5
- **编程语言**: TypeScript
- **UI 组件库**: Naive UI
- **状态管理**: Pinia
- **路由**: Vue Router
- **HTTP 客户端**: Axios
- **图表**: ECharts
- **代码规范**: ESLint + Prettier + Stylelint

## 项目结构

```
src/
├── api/          # API 接口
├── assets/       # 静态资源
├── components/   # 公共组件
├── config/       # 配置文件
├── router/       # 路由配置
├── stores/       # 状态管理
├── styles/       # 样式文件
├── types/        # 类型定义
├── utils/        # 工具函数
└── views/        # 页面组件
```

## 部署

构建完成后，将 `dist` 目录部署到 Web 服务器即可。

## 许可证

MIT License