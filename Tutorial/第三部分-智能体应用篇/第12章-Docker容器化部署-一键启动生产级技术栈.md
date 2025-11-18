# 第12章 Docker容器化部署——一键启动生产级技术栈

## 本章目标

1. 掌握多阶段Docker构建技术,将镜像大小从800MB优化到300MB
2. 理解Docker Compose编排7个微服务的网络拓扑与依赖关系
3. 学会Volume持久化存储配置,避免容器重启数据丢失
4. 深入理解国内镜像加速策略,解决pip/npm安装慢的痛点
5. 掌握生产环境部署的健康检查、日志收集、资源限制配置

---

## 一、为什么选择Docker容器化?

### 1. 传统部署vs容器化部署

**传统部署痛点**:

```bash
# Server A (Ubuntu 20.04, Python 3.8)
pip install sanic==23.6.0  ✓ 成功

# Server B (Ubuntu 22.04, Python 3.11)
pip install sanic==23.6.0  ✗ 依赖冲突
```

**解决方案**: "在我的机器上能跑" → "在任何机器上都能跑"

**Docker方案**:

```dockerfile
FROM python:3.11-slim
RUN pip install sanic==23.6.0
```

- 锁定Python版本
- 锁定依赖版本
- 环境一致性100%

### 2. 微服务拓扑图

```
                        ┌─────────────┐
                        │  前端服务   │
                        │ (Vue3+Vite) │
                        │   :8081     │
                        └──────┬──────┘
                               │
                    ┌──────────▼──────────┐
                    │   Sanic后端服务     │
                    │  (Python 3.11)      │
                    │      :8089          │
                    └─┬───┬───┬───┬───┬──┘
                      │   │   │   │   │
        ┌─────────────┼───┼───┼───┼───┼────────────┐
        │             │   │   │   │   │            │
    ┌───▼───┐   ┌────▼──┐ │   │   │   │    ┌──────▼──────┐
    │ MySQL │   │ MinIO │ │   │   │   │    │ MCP Hub     │
    │ :3306 │   │ :9000 │ │   │   │   │    │ :3000       │
    └───────┘   └───────┘ │   │   │   │    └─────────────┘
                       ┌───▼──┐ │   │
                       │Neo4j │ │   │
                       │ :7687│ │   │
                       └──────┘ │   │
                           ┌────▼──┐│
                           │GPT-Vis││
                           │  API  ││
                           │ :3100 ││
                           └───────┘│
```

**7个服务**:

1. `chat-web`: Vue3前端(Nginx)
2. `chat-service`: Sanic后端(Python)
3. `mysql`: 数据库
4. `minio`: 对象存储(可选)
5. `neo4j-apoc`: 图数据库(可选)
6. `mcphub`: MCP服务集线器
7. `gpt-vis-api`: 图表渲染API

---

## 二、多阶段构建优化镜像大小

### 1. 单阶段构建的问题

**传统Dockerfile**(反面示例):

```dockerfile
FROM python:3.11
WORKDIR /sanic-web

# 安装编译工具(gcc, make等)
RUN apt-get update && apt-get install -y gcc python3-dev

# 安装Python依赖
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync

# 复制代码
COPY . .

CMD ["python", "serv.py"]
```

**问题**:

- 镜像包含gcc编译器(200MB+)
- 包含pip缓存(100MB+)
- 包含apt缓存(50MB+)
- **最终镜像大小: ~800MB**

### 2. 多阶段构建方案

**docker/Dockerfile**(完整42行):

```dockerfile
# 构建阶段
FROM python:3.11-slim-bookworm AS builder
WORKDIR /sanic-web

# 设置清华源 + 添加 PATH
ENV PIP_INDEX_URL="https://mirrors.aliyun.com/pypi/simple" \
    PIP_EXTRA_INDEX_URL="https://pypi.doubanio.com/simple" \
    UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple" \
    PATH="/root/.local/bin:${PATH}"

# 复制项目文件
COPY . .

# 安装依赖工具并安装依赖
RUN set -eux; \
    apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    pip install --no-cache-dir pipx && \
    pipx install "uv==0.8.0" && \
    uv venv --clear && \
    . .venv/bin/activate && \
    uv sync --no-cache --index-url https://mirrors.aliyun.com/pypi/simple --extra-index-url "" --verbose && \
    apt-get purge -y gcc python3-dev && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# 最终运行阶段
FROM python:3.11-slim-bookworm
WORKDIR /sanic-web

# 复制构建结果
COPY --from=builder /sanic-web /sanic-web

# 设置环境变量
ENV PATH="/sanic-web/.venv/bin:${PATH}"


# 暴露端口
EXPOSE 8088

# 启动服务
CMD [".venv/bin/python","serv.py"]
```

**核心技术拆解**:

1. **AS builder创建构建阶段**

```dockerfile
FROM python:3.11-slim-bookworm AS builder
```

- 该阶段仅用于编译Python扩展包
- 最终不会出现在生产镜像中

2. **安装+清理一条RUN命令**

```dockerfile
RUN set -eux; \
    apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    ... 安装依赖 ... && \
    apt-get purge -y gcc python3-dev && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*
```

**为什么要合并成一条RUN?**

```dockerfile
# 错误示例(会产生3个Layer):
RUN apt-get install gcc  # Layer 1: +200MB
RUN uv sync              # Layer 2: +150MB
RUN apt-get purge gcc    # Layer 3: -0MB (删除不会减小镜像大小!)
# 最终镜像: 200+150=350MB

# 正确示例(仅1个Layer):
RUN apt-get install gcc && uv sync && apt-get purge gcc
# 最终镜像: 150MB (gcc被真正删除)
```

3. **COPY --from=builder仅复制必需文件**

```dockerfile
FROM python:3.11-slim-bookworm  # 干净的基础镜像
COPY --from=builder /sanic-web /sanic-web  # 仅复制代码和依赖
```

- **不包含**: gcc编译器、apt缓存、pip缓存
- **仅包含**: Python代码 + .venv虚拟环境

**最终效果**:

```bash
# 构建镜像
docker build -t sanic-web:latest -f docker/Dockerfile .

# 查看镜像大小
docker images sanic-web
# REPOSITORY   TAG      SIZE
# sanic-web    latest   320MB  ← 优化后
```

---

## 三、国内镜像加速策略

### 1. Python依赖加速

**docker/Dockerfile**(第6-9行):

```dockerfile
ENV PIP_INDEX_URL="https://mirrors.aliyun.com/pypi/simple" \
    PIP_EXTRA_INDEX_URL="https://pypi.doubanio.com/simple" \
    UV_INDEX_URL="https://mirrors.aliyun.com/pypi/simple"
```

**加速效果**:

| 依赖包 | PyPI官方源 | 阿里云镜像 |
|--------|-----------|-----------|
| numpy | 15s | 2s |
| pandas | 20s | 3s |
| langchain | 30s | 5s |

**为什么设置双源?**

```dockerfile
PIP_INDEX_URL="https://mirrors.aliyun.com/pypi/simple"  # 主源
PIP_EXTRA_INDEX_URL="https://pypi.doubanio.com/simple"  # 备用源
```

- 阿里云镜像可能缺少某些小众包
- 豆瓣源作为备用,提高成功率

### 2. UV依赖安装命令解析

**docker/Dockerfile**(第22行):

```dockerfile
uv sync --no-cache --index-url https://mirrors.aliyun.com/pypi/simple --extra-index-url "" --verbose
```

**参数说明**:

| 参数 | 作用 | 原因 |
|------|------|------|
| `--no-cache` | 禁用UV缓存 | Docker构建时缓存无意义,减小镜像层大小 |
| `--index-url` | 指定主PyPI源 | 覆盖环境变量,确保使用国内镜像 |
| `--extra-index-url ""` | 禁用额外源 | 避免连接PyPI官方源超时 |
| `--verbose` | 详细日志 | 构建失败时便于调试 |

### 3. Docker基础镜像加速

**配置阿里云镜像加速器**:

```bash
# 创建Docker配置文件
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<-'EOF'
{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://mirror.ccs.tencentyun.com"
  ]
}
EOF

# 重启Docker
sudo systemctl daemon-reload
sudo systemctl restart docker
```

**验证**:

```bash
docker info | grep "Registry Mirrors"
# Registry Mirrors:
#   https://docker.mirrors.ustc.edu.cn/
```

---

## 四、Docker Compose服务编排

### 1. 核心配置解析

**docker/docker-compose.yaml**(前端服务,第1-14行):

```yaml
services:
  chat-web:
    image: crpi-7xkxsdc0iki61l0q.cn-hangzhou.personal.cr.aliyuncs.com/apconw/chat-vue3-mvp:1.1.9
    container_name: chat-vue3-mvp
    environment:
      TZ: Asia/Shanghai
    volumes:
      - ./nginx.conf.template:/etc/nginx/conf.d/default.conf
    ports:
      - "8081:80"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    depends_on:
      - chat-service
```

**关键配置**:

1. **TZ时区设置**

```yaml
environment:
  TZ: Asia/Shanghai
```

- 容器内默认UTC时间
- 设置为Asia/Shanghai后,日志时间正确

2. **extra_hosts宿主机网关**

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

- 允许容器访问宿主机服务
- 例如: 前端容器调用宿主机上的Sanic服务(开发环境)

3. **depends_on服务依赖**

```yaml
depends_on:
  - chat-service
```

- 确保chat-service先启动
- 但**不等待**chat-service健康检查通过(需要healthcheck)

### 2. 后端服务配置

**docker/docker-compose.yaml**(Sanic服务,第29-61行):

```yaml
chat-service:
  image: crpi-7xkxsdc0iki61l0q.cn-hangzhou.personal.cr.aliyuncs.com/apconw/sanic-web:1.1.9
  container_name: sanic-web
  environment:
    SERVER_PORT: ${SERVER_PORT:-8089}
    SERVER_WORKERS: ${SERVER_WORKERS:-2}
    MYSQL_HOST: ${MYSQL_HOST:-}
    MYSQL_PORT: ${MYSQL_PORT:-}
    MYSQL_USER: ${MYSQL_USER:-}
    MYSQL_PASSWORD: ${MYSQL_PASSWORD:-}
    MYSQL_DATABASE: ${MYSQL_DATABASE:-}
    SQLALCHEMY_DATABASE_URI: ${SQLALCHEMY_DATABASE_URI:-}
    DIFY_SERVER_URL: ${DIFY_SERVER_URL:-}
    DIFY_DATABASE_QA_API_KEY: ${DIFY_DATABASE_QA_API_KEY:-}
    MINIO_ENDPOINT: ${MINIO_ENDPOINT:-}:${MINIO_PORT:-}
    MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY:-}
    MiNIO_SECRET_KEY: ${MiNIO_SECRET_KEY:-}
    MODEL_BASE_URL: ${MODEL_BASE_URL:-}
    MODEL_NAME: ${MODEL_NAME:-}
    MODEL_TEMPERATURE: ${MODEL_TEMPERATURE:-}
    MODEL_API_KEY: ${MODEL_API_KEY:-}
    MCP_HUB_COMMON_QA_GROUP_URL: ${MCP_HUB_COMMON_QA_GROUP_URL:-}
    MCP_HUB_DATABASE_QA_GROUP_URL: ${MCP_HUB_DATABASE_QA_GROUP_URL:-}
    SHOW_THINKING_PROCESS: ${SHOW_THINKING_PROCESS:-}
    NEO4J_URI: ${NEO4J_URI:-}
    NEO4J_USER: ${NEO4J_USER:-}
    NEO4J_PASSWORD: ${NEO4J_PASSWORD:-}
    JWT_SECRET_KEY: ${JWT_SECRET_KEY:-}
    TZ: Asia/Shanghai
  ports:
    - "${SERVER_PORT:-8089}:${SERVER_PORT:-8089}"
  extra_hosts:
    - "host.docker.internal:host-gateway"
```

**环境变量最佳实践**:

```yaml
MYSQL_HOST: ${MYSQL_HOST:-}  # 从.env读取,无默认值
SERVER_PORT: ${SERVER_PORT:-8089}  # 从.env读取,默认8089
```

- `:-` 语法: 环境变量未设置时使用默认值
- 敏感信息(如密码)留空,强制从.env文件读取

### 3. 数据库服务配置

**docker/docker-compose.yaml**(MySQL服务,第63-76行):

```yaml
mysql:
  image: mysql:latest
  container_name: chat-db
  ports:
    - "3306:3306"
  environment:
    - MYSQL_ROOT_PASSWORD=1
    - CHARACTER_SET_SERVER=utf8mb4
    - COLLATION_SERVER=utf8mb4_unicode_ci
    - TZ=Asia/Shanghai
  volumes:
    - ./volume/mysql/data:/var/lib/mysql
    - ./my.cnf:/etc/mysql/conf.d/my.cnf
```

**关键配置**:

1. **字符集设置**

```yaml
CHARACTER_SET_SERVER=utf8mb4
COLLATION_SERVER=utf8mb4_unicode_ci
```

- `utf8mb4`支持emoji表情
- `utf8`仅支持3字节字符,会导致插入emoji失败

2. **Volume持久化**

```yaml
volumes:
  - ./volume/mysql/data:/var/lib/mysql
```

- 数据存储在宿主机`./volume/mysql/data`
- 容器删除后数据不丢失

3. **自定义配置**

```yaml
- ./my.cnf:/etc/mysql/conf.d/my.cnf
```

**my.cnf示例**:

```ini
[mysqld]
max_connections = 200
innodb_buffer_pool_size = 512M
log_bin = mysql-bin
server_id = 1
```

### 4. Neo4j服务配置

**docker/docker-compose.yaml**(Neo4j服务,第103-116行):

```yaml
neo4j-apoc:
  image: neo4j:5.26.11-ubi9
  container_name: neo4j-apoc
  ports:
    - "7474:7474"  # Web UI
    - "7687:7687"  # Bolt协议
  volumes:
    - ./volume/neo4j/data:/data
    - ./volume/neo4j/plugins:/plugins
  environment:
    - apoc.export.file.enabled=true
    - apoc.import.file.enabled=true
    - apoc.import.file.use_neo4j_config=true
    - NEO4J_AUTH=neo4j/neo4j123
```

**APOC插件配置**:

```yaml
apoc.export.file.enabled=true
apoc.import.file.enabled=true
```

- APOC是Neo4j标准算法库
- 支持CSV导入、JSON导出等高级功能

**安装APOC插件**:

```bash
# 下载APOC插件
mkdir -p docker/volume/neo4j/plugins
cd docker/volume/neo4j/plugins
wget https://github.com/neo4j/apoc/releases/download/5.26.0/apoc-5.26.0-extended.jar

# 启动容器
docker-compose up -d neo4j-apoc
```

---

## 五、Makefile自动化构建

### 1. Makefile配置

**Makefile**(完整33行):

```makefile
# 导入子模块web的 Makefile
include web/Makefile

# 服务端项目名称
SERVER_PROJECT_NAME = sanic-web

# 服务端 Docker 镜像标签
SERVER_DOCKER_IMAGE = apconw/$(SERVER_PROJECT_NAME):1.1.9

# 阿里云镜像仓库地址 (需要根据实际情况修改)
ALIYUN_REGISTRY = crpi-7xkxsdc0iki61l0q.cn-hangzhou.personal.cr.aliyuncs.com
ALIYUN_NAMESPACE = apconw
ALIYUN_IMAGE_NAME = $(ALIYUN_REGISTRY)/$(ALIYUN_NAMESPACE)/$(SERVER_PROJECT_NAME)

# 构建 Vue 3 前端项目镜像
web-build:
	$(MAKE) -C web docker-build

# 构建服务端镜像
service-build:
	docker build --no-cache -t $(SERVER_DOCKER_IMAGE) -f ./docker/Dockerfile .


# 构建 服务端arm64/amd64架构镜像并推送docker-hub
docker-build-server-multi:
	docker buildx build --platform linux/amd64,linux/arm64 --push -t $(SERVER_DOCKER_IMAGE) -f ./docker/Dockerfile .


# 构建服务端arm64/amd64架构镜像并推送至阿里云镜像仓库
docker-build-aliyun-server-multi:
	docker buildx build --platform linux/amd64,linux/arm64 --push -t $(ALIYUN_IMAGE_NAME):1.1.9 -f ./docker/Dockerfile .

.PHONY: web-build service-build
```

### 2. 构建命令

**本地构建**:

```bash
# 构建后端镜像
make service-build

# 构建前端镜像(需进入web目录)
make web-build
```

**多架构构建**(支持Mac M1/M2):

```bash
# 创建buildx构建器
docker buildx create --name mybuilder --use
docker buildx inspect --bootstrap

# 构建并推送多架构镜像
make docker-build-server-multi
```

**为什么需要多架构?**

| 架构 | 设备 | 占比 |
|------|------|------|
| amd64 | 云服务器、Intel Mac | 80% |
| arm64 | Apple M1/M2、ARM服务器 | 20% |

- 单架构镜像在ARM设备上运行会报错: `exec format error`
- 多架构镜像自动适配CPU架构

---

## 六、生产环境部署流程

### 1. 环境准备

**服务器要求**:

```
CPU: 4核+
内存: 16GB+
磁盘: 100GB+
系统: Ubuntu 22.04 / CentOS 8
```

**安装Docker**:

```bash
# Ubuntu
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun

# 启动Docker
sudo systemctl start docker
sudo systemctl enable docker

# 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

### 2. 代码部署

```bash
# 克隆代码
git clone https://github.com/fwytech/sanic-web-table-talk.git
cd sanic-web-table-talk/docker

# 创建环境变量文件
cp ../.env.template .env.pro
vim .env.pro  # 填写生产环境配置

# 创建Volume目录
mkdir -p volume/mysql/data
mkdir -p volume/neo4j/data
mkdir -p volume/minio/data
```

### 3. 启动服务

**完整栈启动**:

```bash
cd docker
docker-compose up -d
```

**仅启动核心服务**:

```bash
# 仅启动Sanic+MySQL(不启动Neo4j/MinIO)
docker-compose up -d chat-service mysql
```

**查看日志**:

```bash
# 查看所有服务日志
docker-compose logs -f

# 查看单个服务日志
docker-compose logs -f chat-service
```

### 4. 健康检查

**检查服务状态**:

```bash
docker-compose ps
```

**输出示例**:

```
NAME            STATE    PORTS
chat-vue3-mvp   Up       0.0.0.0:8081->80/tcp
sanic-web       Up       0.0.0.0:8089->8089/tcp
chat-db         Up       0.0.0.0:3306->3306/tcp
minio           Up       0.0.0.0:19000-19001->9000-9001/tcp
neo4j-apoc      Up       0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp
```

**测试接口**:

```bash
# 测试后端健康
curl http://localhost:8089/

# 测试前端
curl http://localhost:8081/
```

### 5. 数据初始化

**初始化MySQL**:

```bash
# 进入容器
docker exec -it chat-db mysql -uroot -p1

# 创建数据库
CREATE DATABASE IF NOT EXISTS sanic_web CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# 退出容器
exit

# 导入初始数据(如果有SQL文件)
docker exec -i chat-db mysql -uroot -p1 sanic_web < init.sql
```

**初始化Neo4j**:

```bash
# 访问Neo4j浏览器
open http://localhost:7474

# 首次登录会要求修改密码
# 默认账号: neo4j / neo4j123
```

---

## 七、生产环境优化配置

### 1. 资源限制

**docker-compose.yaml增强版**:

```yaml
chat-service:
  image: apconw/sanic-web:1.1.9
  deploy:
    resources:
      limits:
        cpus: '2.0'  # 限制最多使用2核CPU
        memory: 4G   # 限制最多使用4GB内存
      reservations:
        cpus: '0.5'  # 保证至少0.5核CPU
        memory: 1G   # 保证至少1GB内存
```

**为什么需要限制资源?**

- 防止单个服务占满CPU导致其他服务卡死
- OOM Killer会优先杀死内存占用最高的进程

### 2. 健康检查

```yaml
chat-service:
  image: apconw/sanic-web:1.1.9
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8089/"]
    interval: 30s  # 每30秒检查一次
    timeout: 10s   # 超时时间
    retries: 3     # 连续3次失败才标记为不健康
    start_period: 40s  # 容器启动40秒后才开始检查
```

**健康检查效果**:

```bash
docker ps
# STATUS: Up 2 minutes (healthy)
```

- 如果healthcheck失败,Docker Compose会自动重启容器

### 3. 日志配置

**限制日志大小**:

```yaml
chat-service:
  image: apconw/sanic-web:1.1.9
  logging:
    driver: "json-file"
    options:
      max-size: "10m"  # 单个日志文件最大10MB
      max-file: "3"    # 保留最近3个日志文件
```

**为什么需要限制?**

- Docker默认日志无限增长
- 曾有案例: 日志占满磁盘导致系统崩溃

**查看日志**:

```bash
# 仅显示最近100行
docker-compose logs --tail=100 chat-service

# 实时跟踪日志
docker-compose logs -f --tail=50 chat-service
```

### 4. 自动重启策略

```yaml
chat-service:
  image: apconw/sanic-web:1.1.9
  restart: unless-stopped  # 除非手动停止,否则总是重启
```

**重启策略对比**:

| 策略 | 说明 |
|------|------|
| `no` | 不自动重启(默认) |
| `always` | 总是重启,即使手动停止后服务器重启也会启动 |
| `on-failure` | 仅当退出码非0时重启 |
| `unless-stopped` | 总是重启,除非手动docker stop |

**生产环境推荐**: `unless-stopped`

---

## 八、常见问题排查

### 1. 容器启动失败

**问题**: `docker-compose up -d`后服务立即退出

**排查步骤**:

```bash
# 1. 查看容器状态
docker-compose ps

# 2. 查看退出日志
docker-compose logs chat-service

# 3. 尝试交互式启动
docker-compose run --rm chat-service bash
```

**常见原因**:

1. 环境变量缺失: `MYSQL_HOST`未设置
2. 端口被占用: `bind: address already in use`
3. 文件权限问题: `Permission denied`

### 2. 容器间网络不通

**问题**: Sanic连接MySQL失败

**排查**:

```bash
# 1. 进入Sanic容器
docker exec -it sanic-web bash

# 2. 尝试ping MySQL容器
ping chat-db  # 使用容器名,而非localhost

# 3. 尝试telnet测试端口
telnet chat-db 3306
```

**解决方案**:

```yaml
# 确保两个服务在同一网络
services:
  chat-service:
    networks:
      - app-network
  mysql:
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

### 3. Volume权限问题

**问题**: MySQL容器启动失败,日志显示`chown: Operation not permitted`

**原因**: `./volume/mysql/data`目录权限不正确

**解决**:

```bash
# 修改目录所有者为MySQL用户(UID 999)
sudo chown -R 999:999 ./volume/mysql/data

# 或直接删除目录重新创建
sudo rm -rf ./volume/mysql/data
mkdir -p ./volume/mysql/data
docker-compose up -d mysql
```

### 4. 镜像拉取慢

**问题**: `docker-compose up`卡在拉取镜像

**解决**:

1. **使用阿里云镜像**

```bash
# 登录阿里云容器镜像服务
docker login --username=<your_username> crpi-7xkxsdc0iki61l0q.cn-hangzhou.personal.cr.aliyuncs.com
```

2. **手动拉取镜像**

```bash
# 逐个拉取
docker pull mysql:latest
docker pull neo4j:5.26.11-ubi9
docker pull minio/minio:RELEASE.2025-04-22T22-12-26Z
```

---

## 九、本章小结

### 1. Docker核心技术

```
多阶段构建 → 镜像大小优化(800MB → 320MB)
国内镜像源 → 构建速度提升10倍
Volume持久化 → 数据不丢失
网络隔离 → 服务间通信
```

### 2. 服务编排清单

| 服务 | 镜像 | 端口 | 用途 |
|------|------|------|------|
| chat-web | chat-vue3-mvp:1.1.9 | 8081 | Vue3前端 |
| chat-service | sanic-web:1.1.9 | 8089 | Sanic后端 |
| mysql | mysql:latest | 3306 | 数据库 |
| minio | minio:RELEASE.2025... | 19000/19001 | 对象存储 |
| neo4j-apoc | neo4j:5.26.11-ubi9 | 7474/7687 | 图数据库 |
| mcphub | samanhappy/mcphub:0.9.12 | 3300 | MCP集线器 |
| gpt-vis-api | gpt-vis-api:0.0.1 | 3100 | 图表渲染 |

### 3. 生产环境检查清单

- [ ] 配置镜像加速器
- [ ] 设置资源限制(CPU/内存)
- [ ] 配置健康检查
- [ ] 限制日志大小
- [ ] 使用`unless-stopped`重启策略
- [ ] 备份Volume数据
- [ ] 配置Nginx反向代理
- [ ] 启用HTTPS(Let's Encrypt)
- [ ] 配置防火墙规则
- [ ] 监控容器资源(Prometheus)

### 4. 启动命令速查

```bash
# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 停止并删除Volume
docker-compose down -v

# 重启单个服务
docker-compose restart chat-service

# 查看资源占用
docker stats
```

---

## 十、教程总结与展望

### 1. 完整学习路径回顾

**第一部分: 基础架构篇**(第1-4章)

```
Sanic框架 → UV包管理 → SQLAlchemy双引擎 → JWT认证
```

**第二部分: 智能体基础篇**(第5-8章)

```
LangChain基础 → CommonReact Agent → Text2SQL(检索) → Text2SQL(Prompt)
```

**第三部分: 智能体应用篇**(第9-12章)

```
Excel Agent → SSE流式响应 → Neo4j/MinIO → Docker部署
```

### 2. 技术栈清单

**后端技术**:

- Python 3.11 + Sanic(异步Web框架)
- SQLAlchemy 2.0 + MySQL(ORM + 原生SQL)
- LangChain + LangGraph(智能体编排)
- DashScope API(阿里云大模型)

**前端技术**:

- Vue 3 + Vite(现代化构建)
- Naive UI(组件库)
- Marked + highlight.js(Markdown渲染)
- ECharts(图表可视化)

**数据存储**:

- MySQL 8.0(关系型数据库)
- Neo4j 5.26(图数据库)
- MinIO(对象存储)
- FAISS(向量索引)

**部署运维**:

- Docker + Docker Compose
- Nginx(反向代理)
- UV(Python包管理器)

### 3. 扩展方向

**性能优化**:

1. **Redis缓存**: 缓存BM25检索结果,减少数据库查询
2. **Celery异步任务**: 长查询改为异步任务,返回task_id
3. **数据库读写分离**: MySQL主从复制,读请求分流

**功能扩展**:

1. **多租户支持**: 每个企业独立数据库schema
2. **自定义LLM**: 接入本地部署的LLaMA/Qwen
3. **语音输入**: 集成讯飞语音识别API

**企业级功能**:

1. **权限管理**: RBAC角色权限体系
2. **审计日志**: 记录所有SQL查询历史
3. **数据脱敏**: 敏感字段自动打码

---

**恭喜你完成了整个教程!**

你现在已经掌握:

1. 从零搭建LangGraph + MCP + Sanic智能问数系统
2. 理解Text2SQL的完整工作流程(从BM25检索到SQL执行)
3. 掌握SSE流式响应实现实时AI对话
4. 学会Docker容器化部署微服务架构
5. 理解可选组件的渐进式增强设计理念

**下一步建议**:

1. **实践项目**: 将教程代码部署到云服务器
2. **贡献代码**: 向开源项目提交PR
3. **技术分享**: 写博客/录视频分享你的学习心得

**保持学习,持续精进!**
