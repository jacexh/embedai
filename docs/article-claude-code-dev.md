# 耗时6小时零代码开发一个多模态数据管理平台

> 利用 Claude Code + Skills，从需求到可运行系统，全程不写一行代码

---

## 背景：一个真实的工程需求

做具身机器人的团队有一个绕不开的痛点：**数据管理**。

机器人每天产生大量的 MCAP（ROS 2 原生格式）和 HDF5 录制文件，动辄数百 GB。这些数据需要：

- 上传存储（分块、断点续传）
- 自动解析元数据（话题列表、时长、帧率）
- 质量评分（哪些数据值得用于训练？）
- 人工标注（坐标、时间线、关键点）
- 打包导出（WebDataset、HuggingFace 格式）

市面上没有完全契合这个场景的开源方案。自己开发？传统方式至少需要一个小团队工作数周。

于是我决定试一试：**用 Claude Code 独立完成整个系统的开发**，看看能走多远。

结果超出了预期——**6小时后，一个完整的多模态数据管理平台上线了**。

---

## 最终产物：EmbedAI DataHub

先看结果，再讲过程。

### 系统架构

```
浏览器
  │
  ▼ :3000
Nginx + React 19 前端
  │ 反向代理 /auth /api/v1
  ▼ :8000
Go Gateway（JWT 认证 + 分块上传 + gRPC）
  ├── 代理 → dataset-service（FastAPI）
  └── 代理 → task-service（FastAPI）

后台：
  pipeline worker × 2  消费 Redis Stream，处理 MCAP/HDF5
  export-worker × 2    消费导出队列，生成 WebDataset

存储：PostgreSQL + MinIO（S3）+ Redis
```

### 技术栈

| 层 | 技术选型 |
|----|---------|
| 前端 | TypeScript · React 19 · TanStack Query · Zustand · Tailwind CSS |
| 网关 | Go 1.25 · Gin · pgx · JWT · gRPC |
| 数据集服务 | Python 3.11 · FastAPI · SQLAlchemy(async) · asyncpg |
| 标注任务服务 | Python 3.11 · FastAPI · Label Studio 集成 |
| 数据管道 | Python 3.11 · MCAP · HDF5 · OpenCV · NumPy |
| 导出工作进程 | Python 3.11 · WebDataset · aioboto3 |
| 基础设施 | PostgreSQL 16 · MinIO · Redis 7 · Label Studio |
| 部署 | Docker Compose（开发/生产两套配置） |

### 代码规模

```
113 个源文件（.go / .py / .tsx / .ts）
10,059 行代码
8 个 Docker 服务
1 套 Alembic 数据库迁移
1 套完整的 E2E 集成测试
```

---

## 关键工具：Claude Code + Skills

### Claude Code 是什么

Claude Code 是 Anthropic 推出的 AI 编程助手 CLI 工具，核心能力是：

- **读写整个代码库**：不是片段补全，而是理解项目全局，跨文件修改
- **执行终端命令**：运行测试、调用 API、操作 Docker，真正"端到端"工作
- **持久记忆**：跨会话保留项目上下文，不用每次重新解释背景
- **并行执行**：同时启动多个子 Agent 处理独立任务

### Skills 是什么

Skills（技能）是用户自定义的提示词模板，封装特定领域的最佳实践。使用 `/skill-name` 语法调用，Claude Code 会在执行任务前加载对应的知识库和规范。

本次开发用到的核心 Skills：

| Skill | 作用 |
|-------|------|
| `/system-design` | 从需求推导架构，用 EventStorming + Mermaid 图可视化 |
| `/writing-plans` | 将架构拆解为可执行的分阶段实现计划 |
| `/brainstorming` | 关键技术决策前的方案探索（如导出格式选型） |
| `/database-patterns` | 数据库 Schema 设计和迁移最佳实践 |
| `/api-design` | REST API 设计规范和 OpenAPI 文档 |
| `/react-typescript` | React 19 + TypeScript 组件模式 |
| `/python-code-style` | Python 代码风格和异步模式 |
| `/golang` | Go 惯用法和错误处理模式 |
| `/tdd` | 测试驱动开发流程 |
| `/dispatching-parallel-agents` | 并行化独立开发任务 |
| `/verification-before-completion` | 每阶段完成前的验收检查 |

Skills 的本质是**领域知识的结构化封装**。调用 `/system-design` 时，Claude Code 不只是"帮你画架构图"，而是按照 EventStorming 方法论逐步推导：先识别领域事件，再划分限界上下文，最后出数据流和集成点。这比写一段模糊的提示词效率高出数倍。

---

## 开发过程：6小时的时间线

### 第一阶段：系统设计（约30分钟）

用一段话描述需求，调用 `/system-design`：

```
/system-design

我需要一个具身机器人数据管理平台，支持：
- 上传 MCAP / HDF5 录制文件
- 自动解析话题元数据和质量评分
- 人工标注任务分发（集成 Label Studio）
- 数据集版本管理
- WebDataset 格式导出用于训练
```

Claude Code 输出了：
1. **领域事件图**：从"文件上传"到"模型训练"的完整事件流
2. **服务边界划分**：5个微服务的职责和接口
3. **关键架构决策（ADR）**：比如为什么用 Redis Stream 而不是 Kafka，为什么导出格式优先选 WebDataset

这个阶段最大的收获是**被迫把模糊需求变成清晰规格**。

### 第二阶段：实现计划（约15分钟）

```
/writing-plans
```

Claude Code 把架构拆成了 8 个独立 Phase，每个 Phase 明确：
- 要交付什么（接口/功能）
- 验收标准是什么（测试用例）
- 和其他 Phase 的依赖关系

### 第三阶段：并行开发（约4小时）

这是最有趣的部分。

对于没有依赖关系的 Phase，使用 `/dispatching-parallel-agents` 同时启动多个子 Agent：

```
/dispatching-parallel-agents

同时执行：
- Agent A：Phase 3 数据处理管道（MCAP解析 + 质量评分）
- Agent B：Phase 4 数据集版本管理 API
- Agent C：Phase 5 Label Studio 集成
```

三个 Agent 并行工作，各自在 git worktree 隔离环境中编写代码，互不干扰。完成后 Claude Code 合并结果，处理冲突。

**每个 Agent 都会自动调用对应领域的 Skills**。写 Python 时遵循 `/python-code-style`，设计 API 时遵循 `/api-design`，从不需要手动提醒"记得用 async/await"或"注意 REST 命名规范"。

### 第四阶段：前端开发（约1小时）

```
/react-typescript

基于已有的 API 文档，实现以下页面：
- /episodes  数据录制列表（过滤/分页/质量评分）
- /upload    分块上传界面（拖拽 + 进度条）
- /datasets  数据集版本管理
- /tasks     标注任务分配
- /export    导出任务管理
```

Claude Code 生成了完整的 React 19 组件树，TanStack Query 管理服务器状态，Zustand 管理认证状态，Tailwind CSS 完成样式。全程没有一次"帮我改改颜色"或"对齐这个按钮"的细节调整——样式直接可用。

### 第五阶段：联调与修复（约30分钟）

这里是最能体现 Claude Code 价值的部分。系统第一次运行时，遇到了一系列问题：

**问题1：两个 PostgreSQL 容器端口冲突**

宿主机已有一个 `postgres` 容器占用了 5432 端口，`infra-postgres-1` 的端口映射失效，`make migrate` 写入了错误的数据库，导致 gateway 找不到用户数据。

Claude Code 的诊断过程：
```bash
# 自动执行的诊断命令序列
docker ps --filter "publish=5432" --format "{{.Names}}\t{{.Ports}}"
docker inspect infra-gateway-1 --format '{{.Config.Env}}'
docker exec infra-postgres-1 psql -U embedai -d embedai -c "\dt"
```

三行命令，定位到根本原因：gateway 连接的是 docker 内网的 `infra-postgres-1`（无 schema），而 seed 数据写入了宿主机的另一个 postgres。解决方案：把 migrate 和 seed 改为在 `infra_default` docker 网络内执行。

**问题2：Pipeline worker 静默失败**

上传的 MCAP 文件处理完后状态没有变成 `ready`。日志里什么都没有。

Claude Code 直接在容器内手动触发 processor：

```python
docker exec infra-pipeline-1 python3 -c "
import asyncio
from pipeline.processor import EpisodeProcessor
...
asyncio.run(test())
"
```

报错立刻出现：

```
asyncpg.exceptions.DataError: invalid input for query argument $3:
  {'quality_detail': ...} ('dict' object has no attribute 'encode')
```

asyncpg 不接受 Python dict 作为 JSONB 参数，需要 `json.dumps()`。一行修复。

**问题3：前端 token 读写不一致**

登录后访问任何页面都返回 401。`apiClient` 从 `localStorage["token"]` 读，但 Zustand persist 把 token 存在 `localStorage["auth"]` 的 JSON 对象里。两个 key 对不上，请求头永远没有 Bearer token。

**问题4：dataset-service 返回裸数组导致白屏**

`GET /api/v1/datasets` 返回 `[]`，但前端期望 `{ items: [], total: 0 }`。`data?.items.map(...)` 中 `data?.items` 是 `undefined`，`.map()` 抛出 TypeError，React 渲染崩溃，白屏。

**问题5：task-service 500 错误**

SQLAlchemy `Base` 中缺少 `Project` 和 `Dataset` 表定义，解析 `ForeignKey("projects.id")` 时抛出 `NoReferencedTableError`。

---

每个问题，Claude Code 的处理模式都一致：
1. **先诊断，不猜测**：执行命令收集证据
2. **定位根本原因**：不修表象
3. **最小化修改**：改一行是一行，不重构周边代码

---

## 关键洞察：什么让这次开发真正高效？

### 1. Skills 是"可复用的架构师大脑"

传统提示词是一次性的，每次对话都要重新解释上下文。Skills 把领域专家的知识固化下来，调用 `/database-patterns` 就自动获得"主键用 UUID、时间字段带时区、索引设计原则、迁移脚本规范"这一整套知识，不需要每次重复。

更重要的是，Skills 提供的是**结构化的思考框架**，而不只是代码模板。`/system-design` 会逼着你回答"这个服务的边界在哪里"、"这个事件的发布者和消费者分别是谁"，这些问题在没有 AI 帮助时很容易被跳过。

### 2. 并行 Agent 打破了线性开发的瓶颈

传统开发的瓶颈是人的串行思维：写完 API 再写测试，测试通过了再写前端。Claude Code 的并行 Agent 机制打破了这个约束——独立的功能模块可以真正同时开发。

6小时完成这个项目，并行化至少贡献了 50% 的时间压缩。

### 3. "零代码"的真实含义

"零代码"不是说系统里没有代码。10,000 行代码是真实存在的，每一行都是 Claude Code 写的。

"零代码"的真实含义是：**开发者的精力全部用在"做什么"上，而不是"怎么写"上**。

我在整个过程中做的决策：
- 要支持什么数据格式（MCAP、HDF5）
- 质量评分应该考虑哪些维度（帧率稳定性、传感器完整性）
- 导出格式的优先级（WebDataset > HuggingFace > 裸文件）
- 标注任务的工作流（创建 → 分配 → 提交 → 审核）

我没有做的事：
- 写任何一个函数
- 调试任何一个语法错误
- 查任何一条 SQLAlchemy 文档
- 纠结 React 组件怎么组织

这种分工让我可以以更高的抽象层次思考问题，就像架构师而不是程序员。

### 4. 调试能力是 AI 开发的真正门槛

很多人用 AI 生成代码，但在出问题时束手无策。Claude Code 的调试流程和人类工程师没有本质区别：看日志 → 缩小范围 → 构造最小复现 → 定位根因 → 最小化修复。

区别在于 Claude Code 的执行速度。从"pipeline 没有处理文件"到"定位是 asyncpg JSONB 参数类型问题"，整个过程不到 3 分钟。人工排查同样的问题，可能需要半小时。

---

## 实事求是：这种方式的边界

不是所有项目都适合这种方式，也不是所有问题都能被轻松解决。

**适合的场景：**
- 业务逻辑清晰，技术边界明确的系统
- 使用成熟技术栈（FastAPI、Go/Gin、React），有大量公开参考
- 需求相对稳定，不是在探索阶段

**仍然需要人工判断的地方：**
- **产品决策**：这个功能要不要做？用户真的需要这个吗？
- **性能调优**：生成的代码在高并发下是否够用？需要 profiling
- **安全审计**：JWT 配置、SQL 注入防护、权限模型是否严谨？
- **领域知识**：MCAP 格式的最佳解析策略、质量评分的权重设计，这些需要机器人领域的专业知识

本次开发中，我在质量评分权重和话题 Schema 设计上花了相当多的时间做人工决策。这类"没有标准答案"的领域问题，AI 只能提供选项，最终判断还是得靠人。

---

## 总结

6小时、10,000 行代码、8 个 Docker 服务、1 个可运行的平台。

这不是未来，这是现在已经可以做到的事。

Claude Code + Skills 的组合改变的不是"代码怎么写"，而是**"谁来写代码"**。在这次实验里，我扮演的角色更接近产品经理和架构师，而 Claude Code 是那个真正把需求变成可运行系统的人。

这并不意味着工程师会消失。恰恰相反，它意味着工程师可以把更多精力放在真正有价值的地方：**理解问题本质、做关键技术决策、构建可持续演进的系统**。

至于写 CRUD 接口、配置 Docker Compose、调整 Tailwind 样式——这些事，让 AI 来吧。

---

*项目已开源：https://github.com/jacexh/embedai*

*本文所有代码均由 Claude Code 自动生成，作者未手动编写任何业务代码。*
