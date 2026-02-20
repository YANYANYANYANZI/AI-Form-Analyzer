import streamlit as st
import os
from io import BytesIO
from src.core.analyzer import AIDrivenFormAnalyzer
from src.utils.helpers import set_chinese_font, make_dataframe_safe_for_ui



def main():
    set_chinese_font()

    st.set_page_config(page_title="智能表单分析系统", page_icon="📊", layout="wide")
    st.title("📊 智能表单分析系统 (企业开源版)")

    # 状态初始化
    for key in ['analyzer', 'api_key', 'chat_history', 'data_file_path']:
        if key not in st.session_state:
            st.session_state[key] = None if key in ['analyzer', 'data_file_path'] else (
                [] if key == 'chat_history' else "")

    with st.sidebar:
        st.header("⚙️ 引擎设置")
        api_key = st.text_input("DeepSeek API 密钥", type="password", value=st.session_state.api_key)
        if api_key: st.session_state.api_key = api_key

        if st.button("🔄 清空上下文记忆"):
            if st.session_state.analyzer:
                st.session_state.analyzer.last_executed_code = ""
            st.success("对话与代码记忆已清空！")

        st.markdown("---")
        st.info("架构特性：防腐层隔离 | 智能路由 | 沙箱执行 | 全量兜底")

        st.markdown("---")
        st.caption("👨‍💻 Author: @YANYANYANYANZI（LeronSterYoung）")
        st.markdown("[⭐ 访问 GitHub 开源仓库](https://github.com/YANYANYANYANZI/AI-Form-Analyzer.git)")
        
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("0. RAG 知识注入")
        kb_file = st.file_uploader("上传业务规则字典 (TXT/CSV)", type=["txt", "md", "csv", "xlsx"])

        st.subheader("1. 数据源挂载")
        uploaded_file = st.file_uploader("上传待分析数据 (Excel/CSV)", type=["xlsx", "xls", "csv"])

        # 核心保活机制
        if st.session_state.analyzer and st.session_state.analyzer.raw_data is None and st.session_state.data_file_path:
            st.session_state.analyzer.restore_data(st.session_state.data_file_path)

        # 引擎初始化
        if (kb_file or uploaded_file) and st.session_state.api_key:
            if not st.session_state.analyzer:
                st.session_state.analyzer = AIDrivenFormAnalyzer(api_key=st.session_state.api_key)

            if kb_file and ('loaded_kb' not in st.session_state or st.session_state.loaded_kb != kb_file.name):
                with st.spinner("🧠 注入企业知识..."):
                    success, msg = st.session_state.analyzer.load_custom_knowledge(kb_file)
                    if success: st.session_state.loaded_kb = kb_file.name
                    st.toast(msg)

            if uploaded_file and (
                    'loaded_data' not in st.session_state or st.session_state.loaded_data != uploaded_file.name):
                with st.spinner("📊 数据落盘防腐中..."):
                    st.session_state.data_file_path = st.session_state.analyzer.load_data(uploaded_file)
                    st.session_state.loaded_data = uploaded_file.name

        # 数据防腐 UI 呈现：使用智能安全转换，解除 5 行封印，使用 height 滚动条
        if st.session_state.analyzer and st.session_state.analyzer.raw_data is not None:
            with st.expander("👀 原始数据抽样 (防腐保护生效中)", expanded=True):
                # 传入全量数据，让前端用滚动条展示，不再切断数据
                safe_df = make_dataframe_safe_for_ui(st.session_state.analyzer.raw_data)
                st.dataframe(safe_df, height=300)
                st.caption(f"当前总行数: {len(st.session_state.analyzer.raw_data)} 行")

    with col2:
        # 修复历史记录的 UI 排版
        popover = st.popover("📜 展开历史记录", use_container_width=True)
        with popover:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    if msg["type"] == "text":
                        st.markdown(msg["content"])
                    elif msg["type"] == "code":
                        with st.expander("👨‍💻 查看底层执行代码"):
                            st.code(msg["content"], language="python")
                    elif msg["type"] == "dataframe":
                        # 历史记录里展示前 5 行即可，避免弹窗过长卡顿
                        st.dataframe(make_dataframe_safe_for_ui(msg["content"].head(5)))
                    elif msg["type"] == "plot":
                        st.pyplot(msg["content"])

        st.subheader("2. 交互终端")
        query = st.text_area("输入您的分析需求...")

        if st.button("发送", use_container_width=True) and query and uploaded_file:
            st.session_state.chat_history.append({"role": "user", "type": "text", "content": query})

            # 修复记忆切片问题：保留更完整的上下文，而不是只切 100 字符
            chat_context = ""
            if len(st.session_state.chat_history) > 1:
                recent = [m for m in st.session_state.chat_history[:-1] if m["type"] == "text"][-6:]
                chat_context = "\n".join([f"{m['role']}: {m['content']}" for m in recent])

            with st.spinner("🚦 网关意图识别中..."):
                metadata = st.session_state.analyzer.get_data_metadata()
                route = st.session_state.analyzer.semantic_router(f"{chat_context}\n当前需求: {query}")
                task_type, need_rag, prep_mode = route.get("task_type", "DATA_OP"), route.get("need_rag",
                                                                                              False), route.get(
                    "preprocess_mode", "NONE")
                rag_ctx = st.session_state.analyzer.retrieve_knowledge(query) if need_rag else ""

            cols = st.columns(3)
            cols[0].metric("调度策略", task_type)
            cols[1].metric("RAG 挂载", "命中" if rag_ctx else "挂起")
            cols[2].metric("预处理动作", prep_mode)

            # 纯聊天链路防越权机制 & RAG 注入
            if task_type == "CHAT":
                with st.spinner("🤖 生成回复..."):
                    chat_sys_prompt = f"""
                                【全局核心人设与最高镇压指令】
                                你是一个智能且友善的企业级数据分析助手。
                                1. 灵活交流：你可以和用户进行任何日常闲聊（包括讨论游戏、生活等），保持自然、幽默、友善。
                                2. 绝对红线：你当前处于纯聊天模式，没有代码沙箱执行权限。绝对禁止捏造假的 DataFrame 数据，绝对禁止手写不可执行的 Markdown 代码块来假装处理数据。
                                3. 【知识库状态强隔离】（最重要！）：
                                    - 下方的【当前挂载的知识库内容】是你唯一可以信任的业务规则来源。
                                    - 如果下方的内容为空，则说明当前系统**没有任何知识库**。你必须回答“当前未挂载知识库”，你可以从历史对话记录中翻找过去的规则来回答，但必须明确说明那是旧规则和当前知识库状态，并提醒用户是否认可使用旧知识/规则！
                                当前数据概况:{metadata}
                                【知识库内容】(如有):
                                {rag_ctx}
                                """
                    res = st.session_state.analyzer.client.chat.completions.create(
                        model=st.session_state.analyzer.model,
                        messages=[{"role": "system", "content": chat_sys_prompt}] + [
                            {"role": m["role"], "content": m["content"]} for m in st.session_state.chat_history[-4:] if
                            m["type"] == "text"]
                    )
                    ans = res.choices[0].message.content
                    # 修复 UI 问题：使用 markdown 代替 info，支持长文本自动换行
                    st.markdown(f"**🤖 助手:**\n\n{ans}")
                    st.session_state.chat_history.append({"role": "assistant", "type": "text", "content": ans})

            # Agent 沙箱代码执行链路
            else:
                with st.spinner("🧠 Agent 代码生成与沙箱执行中..."):
                    success, res_dict, code = st.session_state.analyzer.execute_agentic_code(
                        query=query, metadata=metadata, rag_context=rag_ctx,
                        task_type=task_type, preprocess_mode=prep_mode, chat_context=chat_context
                    )

                    # 1. 记录代码（始终记录，便于调试）
                    st.session_state.chat_history.append({"role": "assistant", "type": "code", "content": code})

                    if success and isinstance(res_dict, dict):
                        st.success("✅ 沙箱执行成功")
                        with st.expander("👨‍💻 查看底层执行逻辑"):
                            st.code(code)

                        # --- 核心修复：单点渲染与存储逻辑 ---

                        # A. 文本总结渲染
                        if res_dict.get("text"):
                            st.markdown(f"**💡 分析总结:**\n\n{res_dict['text']}")
                            st.session_state.chat_history.append(
                                {"role": "assistant", "type": "text", "content": res_dict["text"]})

                        # B. 数据表格渲染（去重修复版）
                        current_df = res_dict.get("df")
                        if current_df is not None and hasattr(current_df, 'empty') and not current_df.empty:
                            # 界面渲染
                            st.dataframe(make_dataframe_safe_for_ui(current_df), height=400)

                            # 导出按钮
                            csv_data = current_df.to_csv(index=False).encode('utf-8-sig')
                            st.download_button(
                                label="📥 导出当前数据 (CSV)",
                                data=csv_data,
                                file_name=f"agent_data_{len(st.session_state.chat_history)}.csv",
                                mime="text/csv",
                                key=f"csv_btn_{len(st.session_state.chat_history)}"
                            )

                            # 存入历史（不再重复存入）
                            st.session_state.chat_history.append(
                                {"role": "assistant", "type": "dataframe", "content": current_df})

                        # C. 图表呈现
                        if res_dict.get("fig"):
                            st.pyplot(res_dict["fig"])

                            # 导出高清图
                            img_buf = BytesIO()
                            res_dict["fig"].savefig(img_buf, format="png", bbox_inches='tight', dpi=300)
                            st.download_button(
                                label="🖼️ 导出高清图表 (PNG)",
                                data=img_buf.getvalue(),
                                file_name=f"agent_plot_{len(st.session_state.chat_history)}.png",
                                mime="image/png",
                                key=f"png_btn_{len(st.session_state.chat_history)}"
                            )
                            st.session_state.chat_history.append(
                                {"role": "assistant", "type": "plot", "content": res_dict["fig"]})

                    else:
                        # 失败后的处理逻辑保持不变
                        st.error("⚠️ 沙箱执行崩溃，触发容灾降级")
                        if task_type == "PLOT":
                            fallback_fig = st.session_state.analyzer.generate_chart({"chart_type": "line"})
                            if fallback_fig:
                                st.pyplot(fallback_fig)
                                st.session_state.chat_history.append(
                                    {"role": "assistant", "type": "plot", "content": fallback_fig})

if __name__ == "__main__":
    main()
