import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import json5
import re
import logging
import pandas as pd
logger = logging.getLogger(__name__)


def set_chinese_font():
    """
    初始化 Matplotlib 的中文字体支持。

    遍历系统字体库，寻找可用的中文字体并设置为默认字体，
    同时修复负号('-')在图表中显示为方块的问题。
    """
    try:
        possible_fonts = [
            'Arial Unicode MS', 'SimHei', 'Microsoft YaHei',
            'SimSun', 'KaiTi', 'FangSong', 'STSong', 'DejaVu Sans'
        ]
        available_fonts = set(f.name for f in fm.fontManager.ttflist)

        for font in possible_fonts:
            if font in available_fonts:
                plt.rcParams['font.family'] = font
                break
        else:
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans']

    except Exception as e:
        logger.warning(f"字体初始化警告: {e}")
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']

    plt.rcParams['axes.unicode_minus'] = False


def extract_json_from_response(ai_response: str) -> dict:
    """
    从大模型的文本响应中鲁棒地提取 JSON 数据。

    使用多重降级策略 (直接解析 -> 正则提取对象 -> 正则提取数组 -> Markdown代码块提取 -> 字符容错修复)。

    Args:
        ai_response (str): 大模型返回的原始字符串。

    Returns:
        dict: 解析后的 Python 字典。如果解析彻底失败，返回 None。
    """
    try:
        return json5.loads(ai_response)
    except:
        pass

    extract_patterns = [
        r'\{[\s\S]*\}',  # 匹配大括号
        r'\[[\s\S]*\]',  # 匹配中括号
        r'```json([\s\S]*?)```',  # 匹配 json 代码块
        r'```([\s\S]*?)```'  # 匹配普通代码块
    ]

    for pattern in extract_patterns:
        try:
            match = re.search(pattern, ai_response)
            if match:
                content = match.group(1).strip() if '```' in pattern else match.group()
                return json5.loads(content)
        except:
            continue

    # 终极容错修复
    try:
        fixed_str = ai_response.translate(str.maketrans('：，；（）', ':,;()'))
        fixed_str = fixed_str.replace("'", '"').replace("True", "true").replace("False", "false").replace("None",
                                                                                                          "null")
        return json5.loads(fixed_str)
    except:
        return None



def make_dataframe_safe_for_ui(df: pd.DataFrame) -> pd.DataFrame:
    """
    智能 UI 防腐转换器。
    仅将混合类型 (object) 的列转换为字符串，防止 PyArrow 渲染崩溃。
    保留真正的 int, float 等数值列，确保前端点击表头排序时数值逻辑正常。
    """
    if df is None:
        return None

        # 如果传入的不是 DataFrame (比如是报错字符串)，直接返回空 DataFrame 或原样返回防止崩溃
    if not hasattr(df, 'empty'):
        return pd.DataFrame()

    if df.empty:
        return df

    safe_df = df.copy()
    for col in safe_df.columns:
        # 只拦截危险的 object (混合) 类型
        if safe_df[col].dtype == 'object':
            safe_df[col] = safe_df[col].astype(str)
    return safe_df