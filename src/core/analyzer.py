import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import json
import httpx
import os
import chromadb
from openai import OpenAI
import logging
import re
from src.utils.helpers import extract_json_from_response

logger = logging.getLogger(__name__)


class AIDrivenFormAnalyzer:
    """
    企业级 AI 驱动的数据分析核心引擎 (Agent)。

    集成了防腐数据适配、智能路由、轻量级 RAG 和安全的 Python 沙箱执行器。
    """

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        """
        初始化分析器实例。

        Args:
            api_key (str): 大模型 API 调用凭证。
            model (str, optional): 使用的模型版本。默认 "deepseek-chat"。
        """
        self.api_key = api_key
        self.model = model

        # 数据状态管理
        self.raw_data = None
        self.processed_data = None
        self.last_executed_code = ""

        # 知识库管理
        self.custom_kb_docs = []
        self.business_kb = {
            "TEGDP": "TEGDP的业务计算公式是：能源消耗 / 工业产值。请注意在数据框中创建一个新列来存放结果。",
        }

        # 初始化 ChromaDB 向量库
        try:
            self.chroma_client = chromadb.Client()
            try:
                self.chroma_client.delete_collection("business_kb")
            except:
                pass
            self.collection = self.chroma_client.create_collection("business_kb")
        except Exception as e:
            logger.error(f"ChromaDB 初始化失败: {e}")
            self.collection = None

        # self.client = OpenAI(api_key=self.api_key, base_url="[https://api.deepseek.com](https://api.deepseek.com)")
        # ====== 工业级网络防抖与隔离 ======
        # 强制配置直连客户端，无视系统的全局/局部代理环境变量，防止代理软件阻断
        custom_http_client = httpx.Client(
            trust_env=False,  # 核心！彻底禁用对系统代理环境变量的读取
            transport=httpx.HTTPTransport(retries=3)  # 增加底层网络重试机制
        )

        # 创建OpenAI客户端
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com/v1",
            http_client=custom_http_client
        )


    def load_data(self, uploaded_file) -> str:
        """
        数据防腐层加载机制：加载上传文件并落盘持久化。

        Args:
            uploaded_file: Streamlit 文件上传对象。

        Returns:
            str: 物理落盘的文件绝对路径。

        Raises:
            ValueError: 文件格式不支持时抛出。
        """
        temp_dir = "./temp_data"
        os.makedirs(temp_dir, exist_ok=True)

        file_ext = uploaded_file.name.split('.')[-1].lower()
        file_path = os.path.join(temp_dir, f"current_source.{file_ext}")

        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        if file_ext in ['xlsx', 'xls']:
            self.raw_data = pd.read_excel(file_path)
        elif file_ext == 'csv':
            self.raw_data = pd.read_csv(file_path, encoding='utf-8')
        else:
            raise ValueError("不支持的文件格式，请使用 Excel 或 CSV 文件")

        # 基础列名清理
        self.raw_data.columns = [str(col).strip().replace('\n', '') for col in self.raw_data.columns]
        return file_path

    def restore_data(self, file_path: str) -> bool:
        """从本地路径静默恢复内存数据（防止 UI 刷新导致数据丢失）。"""
        try:
            file_ext = file_path.split('.')[-1].lower()
            if file_ext in ['xlsx', 'xls']:
                self.raw_data = pd.read_excel(file_path)
            elif file_ext == 'csv':
                self.raw_data = pd.read_csv(file_path, encoding='utf-8')
            self.raw_data.columns = [str(col).strip().replace('\n', '') for col in self.raw_data.columns]
            return True
        except Exception as e:
            logger.error(f"本地数据恢复失败: {e}")
            return False

    def get_data_metadata(self, df: pd.DataFrame = None) -> str:
        """
        生成脱敏的数据元信息 (Metadata)。
        绝对禁止将全量数据传递给大模型，仅提取表结构与抽样。
        """
        target_df = df if df is not None else (
            self.processed_data if self.processed_data is not None else self.raw_data)

        if target_df is None:
            return "暂无数据"
        if target_df.empty:
            return "⚠️ 注意：当前数据框为空 (0行)！请检查之前的清洗/过滤操作是否过于严格导致数据全部丢失。"

        metadata = {
            "columns": list(target_df.columns),
            "dtypes": {col: str(dtype) for col, dtype in target_df.dtypes.items()},
            "shape": target_df.shape,
            "missing_values": target_df.isnull().sum().to_dict(),
            "sample_data": target_df.head(3).to_markdown(index=False)
        }
        return json.dumps(metadata, ensure_ascii=False, indent=2)

    def semantic_router(self, query: str) -> dict:
        """多维智能语义路由网关，决定 Agent 的工作模式与预处理策略。"""
        prompt = f"""
        你是一个企业级数据分析系统的智能路由网关。请分析用户的输入意图: "{query}"

        【强匹配判定规则】(按优先级从高到低排列)
        0. 【否定检查】：注意区分用户是单纯包含 "画图","分析","代码",还是要求"不要画图/不要生成图像/不要代码/不要分析"等意图，然后再进一步判断是否跳过。
        1. 【最高优先级 - 知识问答】：如果用户询问"要求"、"红线"、"规则"、"是什么"、"查询定义"等，即使包含"数据"或"清洗"字眼，也【必须】判定为 "CHAT"，并将 "need_rag" 设为 true。
        2. 【画图判定】：只要包含 "画图", "可视化", "图表", "分布", "折线", "柱状图" 等词，判定为 "PLOT"。
        3. 【数据操作】：只要要求 "计算", "分析", "清洗", "汇总", "排序", "提取" 数据，判定为 "DATA_OP"。
        4. 【日常闲聊】：如果是纯聊天、问候、讨论游戏或生活，判定为 "CHAT"，"need_rag" 设为 false。
       【追加判定原则】
        - 只要用户提到“画图”、“分析”、“展示”，即使语气像在聊天，也必须判定为 "PLOT" 或 "DATA_OP"。
        - 只有当用户完全不涉及数据（如问“你好”、“今天天气如何”、“你喜欢什么游戏”）时，才判定为 "CHAT"。
        - 如果用户询问关于“规则”、“红线”或“知识库内容”，判定为 "CHAT" 且 "need_rag": true。
     

        【Few-Shot 示例】
        输入: "数据清洗红线都有什么" -> 输出: {{"task_type": "CHAT", "need_rag": true, "preprocess_mode": "NONE"}}
        输入: "和我聊聊游戏" -> 输出: {{"task_type": "CHAT", "need_rag": false, "preprocess_mode": "NONE"}}
        输入: "生成完整的可视化图表" -> 输出: {{"task_type": "PLOT", "need_rag": false, "preprocess_mode": "DEFAULT"}}
        输入: "帮我把空值填上" -> 输出: {{"task_type": "DATA_OP", "need_rag": false, "preprocess_mode": "CUSTOM"}}
        输入: "帮我画个图，顺便分析下预警省份" -> 输出: {{"task_type": "PLOT", "need_rag": false, "preprocess_mode": "DEFAULT"}}
        
        请严格按照以下JSON格式返回，不要输出任何额外内容：
        {{
            "task_type": "CHAT" | "DATA_OP" | "PLOT",
            "need_rag": true | false,
            "preprocess_mode": "CUSTOM" | "DEFAULT" | "NONE"
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个智能语义路由器，严格输出JSON，不回答任何多余的话。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=200,
                stream=False
            )
            result = extract_json_from_response(response.choices[0].message.content.strip())
            return result if result else {"task_type": "CHAT", "need_rag": False, "preprocess_mode": "NONE"}
        except Exception as e:
            logger.error(f"路由异常: {e}")
            return {"task_type": "CHAT", "need_rag": False, "preprocess_mode": "NONE"}

    def load_custom_knowledge(self, uploaded_file) -> tuple[bool, str]:
        """加载自定义知识库并向 ChromaDB 注入向量化条目。"""
        try:
            ext = uploaded_file.name.split('.')[-1].lower()
            sentences = []
            if ext in ['txt', 'md']:
                content = uploaded_file.getvalue().decode('utf-8')
                content = re.sub(r'\s+', ' ', content)
                sentences = [s.strip() for s in re.split(r'([。！？!?])', content) if len(s.strip()) > 5]
            elif ext in ['csv', 'xlsx', 'xls']:
                df = pd.read_csv(uploaded_file) if ext == 'csv' else pd.read_excel(uploaded_file)
                sentences = [", ".join([f"{col}: {row[col]}" for col in df.columns]) for _, row in df.iterrows()]

            if not sentences:
                return False, "❌ 提取到的知识条目为空"

            self.custom_kb_docs.extend(sentences)
            if self.collection:
                self.collection.add(documents=sentences, ids=[f"doc_{i}" for i in range(len(sentences))])
            return True, f"✅ 成功加载知识库，已注入 {len(sentences)} 条企业规则。"
        except Exception as e:
            return False, f"❌ 知识库加载失败: {str(e)}"

    def retrieve_knowledge(self, query: str) -> str:
        """执行 RAG 检索：结合内置绝对词典与 ChromaDB 向量匹配。"""
        context = ""
        for keyword, definition in self.business_kb.items():
            if keyword.lower() in query.lower():
                context += f"【系统内置知识】: {definition}\n"

        if self.collection and self.collection.count() > 0:
            try:
                results = self.collection.query(query_texts=[query], n_results=min(3, self.collection.count()))
                if results and results['documents'] and results['documents'][0]:
                    context += "【知识库检索结果】:\n" + "\n".join(results['documents'][0]) + "\n"
            except Exception as e:
                logger.error(f"ChromaDB 检索异常: {e}")
        return context.strip()

    def is_safe_code(self, code_str: str) -> tuple[bool, str]:
        """利用 AST 进行静态安全扫描，防止恶意代码注入。"""
        import ast
        try:
            tree = ast.parse(code_str)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    for alias in node.names:
                        if alias.name in ['os', 'sys', 'subprocess', 'shutil', 'requests']:
                            return False, f"禁止导入高危系统模块: {alias.name}"
            return True, ""
        except Exception as e:
            return False, f"代码包含 Python 语法错误: {e}"

    def execute_agentic_code(self, query: str, metadata: str, rag_context: str = "",
                             task_type: str = "DATA_OP", preprocess_mode: str = "NONE",
                             max_retries: int = 3, chat_context: str = "") -> tuple[bool, dict, str]:
        """
        沙箱代码执行器核心链路。
        包含：自动预处理 -> LLM 代码生成 -> AST 扫描 -> 沙箱隔离执行 -> 自我反思重试。
        """
        if self.raw_data is None:
            return False, "核心数据丢失！请在左侧重新上传或刷新数据文件。", ""

        df_current = self.processed_data if self.processed_data is not None else self.raw_data.copy()

        # 静默预处理逻辑
        if preprocess_mode == "DEFAULT" and not df_current.empty:
            original_len = len(df_current)
            df_current.dropna(how='all', inplace=True)
            df_current.drop_duplicates(inplace=True)
            self.processed_data = df_current
            if len(df_current) < original_len:
                chat_context += f"\n[系统内部提示：已静默去除了 {original_len - len(df_current)} 行全空/重复脏数据。]"

        history_context = ""
        if self.last_executed_code:
            history_context = f"【上一步成功执行的代码参考】\n```python\n{self.last_executed_code}\n```\n如果需求是微调，请直接修改上述代码。"

        sys_prompt = f"""
                你是一个精通 Pandas 和 Matplotlib 的高级数据工程师。
                当前操作的数据元信息（Metadata）如下：
                {metadata}
                {rag_context}
                {chat_context}
                {history_context}

                用户的最新需求："{query}"

                【严格执行规则 - 状态机隔离】(极度重要！必须遵守！)
                1. **数据源唯一性**：当前最新的数据已经通过变量 `df` 注入。无论上一步做了什么，你都应该且仅应该从 `df` 获取数据。
                2. **禁止自检逻辑**：绝对禁止在代码中检查 `update_df` 是否存在或是否为 None。`update_df` 是由你定义的输出变量，不是输入变量。
                3. **任务输出隔离**：
                   - **如果你要更新全局底表**（如清洗、新增列）：请处理完后执行 `update_df = 处理后的完整df`。
                   - **如果你只是做局部统计/绘图**：请执行 `result_df = 统计结果表`，不要动 `update_df`。
                4. **绘图规范**：如果涉及绘图，必须将对象赋给 `fig`。
                5. **代码纯净度**：只输出包裹在 ```python 和 ``` 之间代码块，不要包含任何类似“我无法执行”的解释性文字。
                """

        current_prompt = sys_prompt
        last_failed_code = ""

        import io
        from contextlib import redirect_stdout

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": current_prompt}],
                    temperature=0.1, max_tokens=5000, stream=False
                )
                ai_response = response.choices[0].message.content.strip()

                code_match = re.search(r'```python(.*?)```', ai_response, re.DOTALL) or re.search(r'```(.*?)```',
                                                                                                  ai_response,
                                                                                                  re.DOTALL)
                code_str = code_match.group(1).strip() if code_match else ai_response
                code_str = code_str.replace("plt.show()", "")
                last_failed_code = code_str

                is_safe, msg = self.is_safe_code(code_str)
                if not is_safe:
                    current_prompt += f"\n\n[第{attempt + 1}次重试] 安全扫描未通过：{msg}"
                    continue

                plt.close('all')

                # 注入沙箱环境，明确声明 update_df 和 result_df 为 None
                # 将 update_df 初始设为 None 依然保留，但要通过 prompt 告诉 AI 不要检查它
                local_vars = {
                    'df': df_current.copy(),
                    'raw_df': self.raw_data.copy(),
                    'pd': pd, 'np': np, 'plt': plt,
                    'update_df': None,
                    'result_df': None,
                    'fig': None
                }

                # 捕获 print 行为
                f = io.StringIO()
                with redirect_stdout(f):
                    exec(code_str, {}, local_vars)
                printed_text = f.getvalue().strip()

                # 从沙箱中提取结果
                output_data = local_vars.get('result_df')
                update_data = local_vars.get('update_df')
                output_fig = local_vars.get('fig')

                if output_fig is None:
                    fig_candidate = plt.gcf()
                    if fig_candidate.get_axes():
                        output_fig = fig_candidate

                if output_data is None and update_data is None and output_fig is None and not printed_text:
                    current_prompt += f"\n\n[第{attempt + 1}次重试] 代码执行没报错，但既没有生成图表(fig)，没输出报表(result_df/update_df)，也没有打印任何总结(print)！请检查。"
                    continue

                # ====== 核心：数据状态机隔离生效 ======
                sys_msg = ""
                show_df = None

                # 1. 只有检测到 update_df，才真正覆写全局底表
                if update_data is not None:
                    self.processed_data = update_data
                    sys_msg = f"\n[⚙️ 系统底层状态：已成功使用 {len(update_data)} 行的新数据覆盖了全局内存底表]"
                    # 如果没有 result_df，才默认展示更新后的底表前几行
                    show_df = update_data

                # 2. 报表优先级最高：如果有 result_df，强制只展示它，不展示底表
                if output_data is not None:
                    show_df = output_data

                self.last_executed_code = code_str
                final_text = f"{printed_text}\n{sys_msg}".strip()

                return True, {"df": show_df, "fig": output_fig, "text": final_text}, code_str


            except Exception as e:
                import traceback
                current_prompt += f"\n\n[第{attempt + 1}次崩溃] 报错:\n{e}\nTraceback:\n{traceback.format_exc()}\n请修复。"

        # 修改 analyzer.py 约 310 行
        return False, {"df": None, "fig": None, "text": "Agent反思重试均失败，触发兜底。"}, last_failed_code

    def generate_chart(self, config: dict):
        """终极兜底图表渲染引擎 (不依赖大模型动态代码)。"""
        plt.rcParams['axes.unicode_minus'] = False
        fig, ax = plt.subplots(figsize=(10, 6))
        try:
            if not self.processed_data.empty and len(self.processed_data.columns) >= 2:
                ax.plot(self.processed_data.iloc[:, 0], self.processed_data.iloc[:, 1], marker='o')
                ax.set_title("基础数据趋势 (兜底渲染)", fontsize=14)
            else:
                ax.plot([1, 2, 3], [1, 2, 3], marker='x')
                ax.set_title("无有效数据", fontsize=14)
            ax.grid(True)
            plt.tight_layout()
            return fig
        except:
            plt.close()
            return None