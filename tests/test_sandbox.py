import pytest
import pandas as pd
from unittest.mock import MagicMock
from src.core.analyzer import AIDrivenFormAnalyzer


class TestAgentSandbox:
    """测试沙箱代码执行器、AST 安全拦截与数据状态机"""

    @pytest.fixture
    def analyzer(self):
        """初始化 Agent，并强行注入一份测试底表数据"""
        agent = AIDrivenFormAnalyzer(api_key="sk-dummy-key-for-testing")
        # 伪造一份内存中的底表数据
        agent.raw_data = pd.DataFrame({"日期": ["2023", "2024"], "工业产值": [100, 200]})
        agent.processed_data = None  # 初始状态下，处理进度表为空
        return agent

    def test_ast_security_interception(self, analyzer):
        """测试 1：AST 静态代码扫描能否成功拦截高危操作"""
        # 测试恶意代码
        dangerous_code = "import os\nos.system('rm -rf /')\nresult_df = df"
        is_safe, msg = analyzer.is_safe_code(dangerous_code)
        assert not is_safe
        assert "禁止导入高危系统模块" in msg

        # 测试正常代码
        safe_code = "import pandas as pd\nimport numpy as np\nresult_df = df.copy()"
        is_safe, msg = analyzer.is_safe_code(safe_code)
        assert is_safe
        assert msg == ""

    def test_state_machine_read_only_view(self, analyzer, mocker):
        """测试 2：当大模型只进行分析 (返回 result_df) 时，是否完美保护了全局底表"""
        mock_response = MagicMock()
        # 模拟大模型生成了一段算平均值的代码，赋给 result_df
        mock_response.choices[0].message.content = "```python\nresult_df = pd.DataFrame({'平均产值': [150]})\n```"
        mocker.patch.object(analyzer.client.chat.completions, 'create', return_value=mock_response)

        success, res_dict, code = analyzer.execute_agentic_code(query="算一下平均值", metadata="{}")

        assert success
        # 前端应该能拿到这个仅有 1 行的计算结果表
        assert len(res_dict["df"]) == 1

        # 【核心断言】：全局底层 processed_data 必须仍然是 None，绝不能被刚才的 1 行数据污染！
        assert analyzer.processed_data is None

    def test_state_machine_global_update(self, analyzer, mocker):
        """测试 3：当大模型执行数据清洗 (返回 update_df) 时，是否成功覆写了全局底表"""
        mock_response = MagicMock()
        # 模拟大模型生成了一段新增列的代码，赋给 update_df
        mock_response.choices[0].message.content = "```python\nupdate_df = df.copy()\nupdate_df['新列'] = 1\n```"
        mocker.patch.object(analyzer.client.chat.completions, 'create', return_value=mock_response)

        success, res_dict, code = analyzer.execute_agentic_code(query="新增一列", metadata="{}")

        assert success
        # 【核心断言】：全局底层 processed_data 被成功唤醒并覆写
        assert analyzer.processed_data is not None
        assert "新列" in analyzer.processed_data.columns