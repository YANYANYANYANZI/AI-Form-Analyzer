import pandas as pd
import numpy as np
import os


def generate_environmental_data():
    """生成包含逼真业务噪点的历年各省份GDP与排放数据"""

    provinces = [
        "北京市", "天津市", "河北省", "山西省", "内蒙古自治区", "辽宁省", "吉林省", "黑龙江省",
        "上海市", "江苏省", "浙江省", "安徽省", "福建省", "江西省", "山东省", "河南省",
        "湖北省", "湖南省", "广东省", "广西壮族自治区", "海南省", "重庆市", "四川省", "贵州省",
        "云南省", "西藏自治区", "陕西省", "甘肃省", "青海省", "宁夏回族自治区", "新疆维吾尔自治区"
    ]
    years = [2019, 2020, 2021, 2022, 2023]

    data = []
    for year in years:
        for prov in provinces:
            # 模拟基础数据：东部沿海高GDP，中西部偏低
            base_gdp = np.random.uniform(10000, 120000) if prov in ["广东省", "江苏省", "山东省",
                                                                    "浙江省"] else np.random.uniform(1000, 50000)
            # 排放量与GDP有一定正相关，但加入随机扰动
            base_emission = base_gdp * np.random.uniform(0.08, 0.25)

            # 90% 的正常数据，10% 的脏数据（用于测试 AI 清洗能力）
            rand_val = np.random.rand()
            if rand_val > 0.95:
                remark = "待核查"
                base_emission = np.nan  # 故意制造空值
            elif rand_val > 0.90:
                remark = "数据异常"
                base_gdp = -999  # 故意制造异常负值
            else:
                remark = "已核实"

            data.append({
                "年份": year,
                "省份": prov,
                "GDP_亿元": round(base_gdp, 2),
                "工业排放量_万吨": round(base_emission, 2) if pd.notna(base_emission) else np.nan,
                "备注": remark
            })

    df = pd.DataFrame(data)

    # 确保目录存在
    output_dir = "data/mock_data"
    os.makedirs(output_dir, exist_ok=True)

    # 导出为 Excel
    output_path = os.path.join(output_dir, "历年各省份GDP和工业排放数据.xlsx")
    df.to_excel(output_path, index=False)
    print(f"✅ 成功生成带业务噪点的测试报表: {output_path} (共 {len(df)} 行)")


if __name__ == "__main__":
    generate_environmental_data()