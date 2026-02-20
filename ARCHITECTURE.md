🏗️ AI Form Analyzer 核心架构设计文档 (Architecture)
本文档旨在说明 AI Form Analyzer 的底层架构设计、数据流转机制以及为解决“大模型落地企业场景”所做的工程化妥协与创新。

1. 系统设计理念 (Design Philosophy)
在传统的“AI+数据分析”尝试中，往往采用将数据发送给 LLM，或直接 eval() 执行 LLM 返回代码的粗暴方式。这在企业级应用中面临三大痛点：数据不出域（隐私安全）、代码不可控（系统安全）、操作不可逆（数据灾难）。

为此，本系统基于 “大模型仅作推理大脑，本地沙箱负责受控执行” 的理念，设计了以下核心架构机制：

防腐层与状态机 (Anti-Corruption & State Machine)：拦截破坏性操作，保护数据底表。

多维语义路由 (Semantic Router)：让不同意图走不同管线，降低大模型幻觉。

AST 沙箱安全 (AST-based Sandbox)：在系统级层面阻断高危系统调用。

自愈与降级兜底 (Self-Healing & Fallbacks)：保障服务端永不白屏崩溃。

2. 核心架构图 (System Architecture)
代码段
graph TD
    User([用户输入 Query]) --> UI[Streamlit 前端交互层]
    UI --> Router{Semantic Router\n(智能语义路由网关)}
    
    Router -- 闲聊 / 答疑 --> ChatAgent[Chat Pipeline]
    Router -- 数据清洗/变更 --> DataOpAgent[Data OP Pipeline]
    Router -- 数据可视化 --> PlotAgent[Plot Pipeline]
    
    DataOpAgent & PlotAgent --> Metadata[Metadata 适配层\n提取表头/类型/统计特征]
    DataOpAgent & PlotAgent --> RAG[(ChromaDB 向量知识库\n注入企业规章与黑话)]
    
    Metadata & RAG --> PromptBuilder[Prompt 构造器]
    PromptBuilder --> LLM((DeepSeek / LLM API))
    
    LLM -- 返回 Python 代码 --> AST[AST 静态安全扫描器]
    AST -- 危险代码 --> Block[阻断并返回安全警告]
    AST -- 安全代码 --> Sandbox[本地安全执行沙箱]
    
    Sandbox -- 执行崩溃抛出 Exception --> Reflection[Self-Reflection 错误堆栈反思]
    Reflection -- 携带 Traceback 重试 (Max:3) --> LLM
    
    Sandbox -- 执行成功 --> StateMachine{读写分离状态机}
    
    StateMachine -- 产出 update_df --> WriteBase[(覆写本地内存底表)]
    StateMachine -- 产出 result_df --> ReadOnly[生成只读视图供 UI 渲染]
    
    WriteBase & ReadOnly --> UI
    
    Reflection -- 彻底失败 --> Fallback[终极降级引擎\n(本地硬编码图表渲染)]
    Fallback --> UI
3. 核心模块详解 (Core Modules)
3.1 多维语义路由网关 (semantic_router)
为了避免大模型将普通的问询误当成数据操作指令，我们在入口处实现了一个轻量级的路由网关。
通过解析用户自然语言，系统强制将任务归类为以下三种枚举状态之一，并走不同的执行上下文：

CHAT：普通的系统问答，不调用代码沙箱。

DATA_OP：数据清洗、特征工程、填补空值等会改变数据本身的操作。

PLOT：数据提取、报表生成、可视化等不改变原始数据的操作。

3.2 Metadata 数据防腐层
解决痛点：数据隐私泄露与 Token 溢出。
系统绝对不会将真实的行级数据发送给 OpenAI/DeepSeek 的 API。在代码生成前，系统仅提取：

DataFrame 的 Column Names

Dtypes (数据类型)

df.head(3) 的结构范例

大模型依靠这些 Metadata 作为“地图”编写代码，真实数据仅在本地物理机的沙箱中流转。

3.3 本地安全执行沙箱 (AST Sandbox)
解决痛点：AI 恶意/失控代码攻击。
在调用 exec() 之前，代码字符串必须经过 is_safe_code 验证：

利用 Python 内置的 ast (Abstract Syntax Tree) 模块解析代码语法树。

拦截器会遍历所有 ast.Import、ast.ImportFrom 和 ast.Call 节点。

一旦发现引入了 os, sys, subprocess 等高危系统模块，或者尝试执行外部命令，立即阻断并警告。

3.4 读写分离状态机 (State Machine)
解决痛点：大模型由于幻觉导致数据全删或截断。
沙箱执行环境被严格约定了两个输出挂载点：

result_df：只读视图。大模型进行查询、聚合计算时，必须将结果赋给此变量。UI 层仅做展示，底层原始 DataFrame 保持不变。

update_df：全局覆写。只有当路由判定为 DATA_OP 时，大模型才被允许使用此变量。一旦沙箱产出了 update_df，系统才会用其覆写全局内存底表，实现数据的持久化清洗。

3.5 带有堆栈反思的自愈机制 (Self-Reflection)
解决痛点：动态代码环境下的高频报错。

代码在沙箱中执行报错（如拼写错误、Pandas 索引越界等）。

try-except 捕获异常，并提取 traceback.format_exc()。

系统将报错信息连同原始代码重新发回给大模型：“[第 X 次崩溃] 报错: {...}，请修复”。

支持最大 3 次自动重试，对用户完全透明。

3.6 轻量级企业 RAG 挂载 (chroma_client)
通过嵌入本地的 ChromaDB，系统支持动态挂载企业的“业务黑话”和“红线规章”。例如注入：“TEGDP 的业务计算公式是：能源消耗 / 工业产值”。当用户提出计算 TEGDP 时，RAG 模块会召回该公式并拼接至 Prompt 中，强制 AI 遵守企业统计口径。

4. 目录结构说明 (Directory Structure)
Plaintext
📦 AI-Form-Analyzer
 ┣ 📂 src                    # 核心业务逻辑
 ┃ ┣ 📜 analyzer.py          # 核心 Agent 引擎、状态机与沙箱环境
 ┃ ┗ 📜 helpers.py           # 通用工具（JSON 容错解析、UI 防腐化渲染、中文字体修补）
 ┣ 📂 tests                  # 单元测试与集成测试矩阵
 ┃ ┣ 📜 test_helpers.py      # 工具函数鲁棒性测试
 ┃ ┣ 📜 test_router.py       # 多维路由判定边界测试
 ┃ ┗ 📜 test_sandbox.py      # AST 拦截与状态机越权测试
 ┣ 📜 app.py                 # Streamlit 前端交互入口与 Session 维护
 ┣ 📜 run.py                 # 基础环境修补（如 macOS 代理 Bug 处理）与启动脚本
 ┣ 📜 requirements.txt       # 系统依赖
 ┗ 📜 README.md              # 项目简述
5. 演进路线图 (Roadmap)
当前的 PoC 版本在单机内存中闭环了核心验证。为了向真正的生产级可用迈进，后续架构规划如下：

持久化存储接入：从单机 pd.DataFrame 升级为对接企业 MySQL/PostgreSQL 数据源的增量执行。

多租户隔离：使用 Docker 容器级别的 Sandbox 替代当前的纯 AST Python Sandbox，实现物理级别的执行隔离。

记忆链持久化：将会话历史 st.session_state.chat_history 转储至 Redis，支持分布式的断点续连。
