import pandas as pd
import pytest
from src.utils.helpers import extract_json_from_response, make_dataframe_safe_for_ui


class TestHelpers:
    """测试底层通用工具类的鲁棒性"""

    def test_extract_json_from_response_perfect(self):
        """测试完美的 JSON 字符串能否被解析"""
        perfect_json = '{"task_type": "PLOT", "need_rag": false}'
        result = extract_json_from_response(perfect_json)
        assert result["task_type"] == "PLOT"
        assert result["need_rag"] is False

    def test_extract_json_from_response_dirty_markdown(self):
        """测试被 Markdown 代码块包裹，甚至带有前言后语的脏 JSON 能否被解析"""
        dirty_response = """
        好的，我已经分析了用户的意图，以下是结果：
        ```json
        {
            "task_type": "DATA_OP",
            "preprocess_mode": "DEFAULT"
        }
        ```
        希望这能帮到您！
        """
        result = extract_json_from_response(dirty_response)
        assert result is not None
        assert result["task_type"] == "DATA_OP"
        assert result["preprocess_mode"] == "DEFAULT"

    def test_make_dataframe_safe_for_ui(self):
        """测试 UI 防腐函数：确保只将 object 列转为 str，保留纯数值列"""
        # 创建一个混合了纯数字和字符串的数据框
        df = pd.DataFrame({
            '纯数字列': [1, 2, 3],
            '混合列': [1, "字符串", 3.14],
            '纯文本列': ["A", "B", "C"]
        })

        safe_df = make_dataframe_safe_for_ui(df)

        # 1. 断言纯数字列的类型没有被破坏 (依然是 int64)
        assert safe_df['纯数字列'].dtype == 'int64'

        # 2. 断言混合列和纯文本列变成了 object (在 Pandas 中 str 就是 object)
        # 并且其中的元素变成了纯粹的字符串格式
        assert type(safe_df['混合列'].iloc[0]) == str
        assert safe_df['混合列'].iloc[0] == "1"