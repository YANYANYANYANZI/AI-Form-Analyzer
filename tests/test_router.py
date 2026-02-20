import pytest
from unittest.mock import MagicMock
from src.core.analyzer import AIDrivenFormAnalyzer


class TestSemanticRouter:
    """测试多维智能路由网关的解析与容错能力"""

    @pytest.fixture
    def analyzer(self):
        """Pytest Fixture：为每个测试用例初始化一个带假 Key 的 Analyzer"""
        return AIDrivenFormAnalyzer(api_key="sk-dummy-key-for-testing")

    def test_router_normal_json_parsing(self, analyzer, mocker):
        """测试 1：当大模型正常返回标准 JSON 时，路由能否正确解析"""
        # 1. 制造一个假的 LLM 返回对象
        mock_response = MagicMock()
        mock_response.choices[
            0].message.content = '{"task_type": "PLOT", "need_rag": false, "preprocess_mode": "DEFAULT"}'

        # 2. 劫持底层 client.chat.completions.create 方法，让它直接返回假对象，不走网络
        mocker.patch.object(analyzer.client.chat.completions, 'create', return_value=mock_response)

        # 3. 触发系统逻辑
        result = analyzer.semantic_router("帮我画个各省份绿色发展指数的柱状图")

        # 4. 断言判定
        assert result["task_type"] == "PLOT"
        assert result["need_rag"] is False
        assert result["preprocess_mode"] == "DEFAULT"

    def test_router_dirty_markdown_parsing(self, analyzer, mocker):
        """测试 2：当大模型啰嗦并返回带 Markdown 的 JSON 时，工具类能否兜底解析"""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = '''
        好的，分析完毕，结果如下：
        ```json
        {
            "task_type": "DATA_OP",
            "need_rag": true,
            "preprocess_mode": "CUSTOM"
        }
        ```
        '''
        mocker.patch.object(analyzer.client.chat.completions, 'create', return_value=mock_response)

        result = analyzer.semantic_router("查一下数据清洗红线，然后把空值全删了")

        assert result["task_type"] == "DATA_OP"
        assert result["need_rag"] is True
        assert result["preprocess_mode"] == "CUSTOM"

    def test_router_api_timeout_fallback(self, analyzer, mocker):
        """测试 3：当大模型 API 彻底宕机（超时/断网）时，系统是否会安全降级为 CHAT"""
        # 劫持底层方法，让它强行抛出网络异常
        mocker.patch.object(analyzer.client.chat.completions, 'create', side_effect=Exception("API Timeout Exception!"))

        # 触发系统逻辑，如果这里没报错，说明 try...except 兜底成功
        result = analyzer.semantic_router("随便聊聊")

        # 断言是否成功降级为了最安全的默认状态
        assert result["task_type"] == "CHAT"
        assert result["need_rag"] is False
        assert result["preprocess_mode"] == "NONE"