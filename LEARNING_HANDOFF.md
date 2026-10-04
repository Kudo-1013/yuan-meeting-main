# Yuan-Meeting 学习交接

## 已有基础

- 用户完成 React Todolist 和必要 Python 基础，包括容器、函数、类型标注、Pydantic、异常、装饰器、上下文管理器、异步、pathlib、logging 和 httpx。
- Hello-Agents 阶段已经跑通通义千问真实模型调用、工具选择、Python 动态执行、结果回传和多轮 Agent 循环。
- 用户能解释 `messages`、`tool_calls`、工具调用结果回传、循环结束条件、异常 Observation 和 `max_steps`。
- 已理解 ReAct、Plan-and-Solve、Reflection 和防止无依据补全信息。

## 学习顺序

1. 最少量 LangChain：`ChatOpenAI`、`SystemMessage`、`HumanMessage`、`invoke/ainvoke`。
2. LangGraph 核心：State、Node、Edge、条件路由、循环、并行 fan-out 和 `END`。
3. 项目 Agent 主链路：Planner → Budget Check → 各分析 Agent → Output Validator → Human Review → Persist。
4. RAG 链路：文档解析与切分 → Embedding → 向量/全文检索 → RRF → 上下文注入 → 生成。
5. 把实际代码整理为能够用于简历和面试的技术说明，并区分已验证事实与待验证描述。

## 重点文件

- `backend/app/agents/nodes/planner.py`
- `backend/app/agents/meeting_graph.py`
- `backend/app/agents/meeting_graph_v2.py`
- `backend/app/agents/nodes/output_validator.py`
- `backend/app/services/summary_service.py`
- `backend/app/services/knowledge_service.py`
- `backend/app/services/chat_service.py`
- `backend/app/services/document_chunker.py`

## 当前阶段：面试整合（2026-10-04）

Python、Hello-Agents 最小闭环及本项目四条工作已经学习过一遍。下一阶段是串联表达、选型取舍和面试追问，不从 Planner 或 Python 基础重新开始。

项目目录：`C:\Users\86187\Desktop\yuan-meeting-main`。

GitHub：`https://github.com/Kudo-1013/yuan-meeting-main`。

### 新聊天先读

1. `AGENTS.md`、`README.md` 和本文件。
2. 本机 `准备文档/面试整合/00-阅读说明与资料出处.md`。
3. 同目录的 `01-四条工作拆解与八股对应.md`、`02-四条工作口述稿.md`、`03-真实问题与修复案例.md`、`04-笔记纠错记录.md`。

准备文档目前按原 Git 忽略规则保留在本机；仅克隆 GitHub 的新环境不包含这些材料。需要在上述本机项目目录中继续。

### 已完成材料

- 四条工作：Multi-Agent 协同编排、RAG 知识增强检索、AI 流式对话与会话管理、长文本与工程化性能优化。
- 已整理43个追问、源码入口、八股关联及小圆老师文章出处。
- 每条已有简短开场、完整口述稿、备选方案与实现边界。
- 三个案例：Vite分组错误、SSE恢复与主动取消、rAF完整缓冲与旧回调隔离。后两者是开发完善/风险验证，不能包装为线上事故。
- 2026-10-03：校对18份原笔记；虚拟列表示例23个边界用例通过，取消六组与恢复八组离线测试通过。这是已有验证，后续不要说成新聊天刚执行的测试。

### 继续的方式

- 从一份简短的项目整体介绍开始，串起“转写→Agent→落库/索引→RAG→流式对话→前端性能”。
- 再按四条工作的顺序，每次只推进一个表达或追问，不一次性堆整套八股。
- 对已有口述稿做脱稿验证；重点追问为什么、替代方案、失败处理、验证证据及个人实际参与。
- 前端岗位重点展开第三、第四条；前两条要能解释业务和真实调用链。
- 用户希望严格基于 supplied 材料和现行源码，小出入不用重构，只修真实错误。修改笔记或实现前先明确当前任务范围。

### 必须保留的事实边界

- LangGraph 负责状态图编排，LangChain 提供模型/消息抽象。
- 人工审核直接放行，Persist节点仅标记；真正落库在服务层，当前未启用图checkpointer。
- RAG的Rerank是关键词启发式；知识内层向量/全文、对话外层文档/决策是两层融合。
- SSE生成任务独立于连接：同生成ID与seq恢复，停止走显式取消；缓存单进程、不能跨重启恢复。
- rAF合并完整缓冲的React提交，未实现逐字符定速动画或稳定块Markdown增量解析。
- 虚拟列表主要用于转写与聊天；知识搜索页目前普通列表。
- 简历描述按用户要求保留。LCP 3.2→2.1没有同条件前后证据；一次约2.9秒报告不能证明该降幅。准备表达时区分实现、实测和待验证数字。
- 不能把辅导中读懂/修改的项目说成全部独立从零开发，也不能编造线上用户量或事故。

### 本机参考资料

- 原笔记：`准备文档`。
- 小圆老师文章合集：`C:\Users\86187\Documents\Codex\2026-09-23\https-www-yuque-com-guluguluwater-qkq0t\outputs\前端全量八股+文章`。
- 本次整合文档的00已提供具体文章链接，不需重新通读整个合集。

