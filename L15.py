import json
from langchain_openai import ChatOpenAI
# 从langchain_experimental.agents中导入用于构建Pandas Agent的类
from langchain_experimental.agents import create_pandas_dataframe_agent
# 导入pandas模块，将其命名为pd
import pandas as pd
# 导入绘图模块 matplotlib，设置非交互式后端
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# 用来绘图的函数
import matplotlib.pyplot as plt
import platform

def setup_plot():
    """全局绘图配置（字体、画布、样式）"""
    import matplotlib.font_manager as fm

    # 根据平台选择中文字体
    system = platform.system()
    if system == "Windows":
        font_name = "Microsoft YaHei"
    elif system == "Darwin":
        font_name = "Arial Unicode MS"
    else:
        font_name = "WenQuanYi Zen Hei"

    # 强制重建字体缓存（确保新安装的字体被识别）
    fm._load_fontmanager(try_read_cache=False)
    plt.rcParams["font.sans-serif"] = [font_name]
    plt.rcParams["axes.unicode_minus"] = False  # 正常显示负号
    plt.figure(figsize=(8, 5))  # 统一画布大小
    plt.grid(True, linestyle="--", alpha=0.5)  # 默认网格线


def ensure_dir(path):
    import os
    """确保保存目录存在"""
    # 提取出文件所在的文件夹路径
    dir_name = os.path.dirname(path)
    # 如果文件夹不存在，就自动创建
    if dir_name and not os.path.exists(dir_name):
        os.makedirs(dir_name)


def draw_chart(data):
    """ 根据AI给出的数据绘制图表
    data：{
        chart_type: "bar" | "line" | "scatter"
        "x": [...],
        "y_series": {"系列1": [...], "系列2": [...]},
        "title": "标题",
        "xlabel": "X轴名",
        "ylabel": "Y轴名"
    }
    """
    # 如果不包含 chart_type 证明无须画图
    if not data.get('chart_type'):
        return ''
    # 绘图全局设置：中文字体、画布大小、网格线等；
    setup_plot()
    # 根据标题生成图像保存路径，例如 artifacts/销售趋势.png
    save_path = f"artifacts/{data.get('title', 'default_chart')}.png"
    # 检查文件目录是否存在
    ensure_dir(save_path)

    # 从data中提取图表类型、x轴数据与y轴数据
    chart_type = data['chart_type']
    x = data["x"]
    y_series = data["y_series"]

    '''根据不同的类型绘图'''
    # 当需要绘制柱状图时
    if chart_type == "bar":
        # 计算每组柱子的宽度，使多组柱状图不会重叠
        width = 0.8 / len(y_series)
        # 使用 enumerate 遍历每个系列（例如“用户数”“转化率”）
        for i, (label, y_values) in enumerate(y_series.items()):
            plt.bar(
                # 设置每组柱子的水平位置
                [p + i * width for p in range(len(x))],
                # 设置柱状图的高度、宽度与标签名称
                y_values, width=width, label=label)

        # 设置 X 轴的刻度标签，使它们与每组柱子的中心位置对齐
        plt.xticks([p for p in range(len(x))], x)

    # 当需要绘制折线图时
    elif chart_type == "line":
        for label, y_values in y_series.items():
            plt.plot(
                x, y_values,  # x轴和y轴数据
                marker="o",  # 用圆圈标出每个点
                label=label)  # 标签名称
    # 当需要绘制散点图时
    elif chart_type == "scatter":
        for label, y_values in y_series.items():
            plt.scatter(x, y_values,  # 每个点的 x 和 y 坐标
                        label=label)  # 图例显示该系列名称

    else:
        # 无法生成图表的数据返回空字符串
        return ''

    '''设置通用的图表样式'''
    # 设置图表标题
    plt.title(data.get("title", "数据分析图表"))
    # 设置 X 轴标题
    plt.xlabel(data.get("xlabel", "X轴"))
    # 设置 Y 轴标题
    plt.ylabel(data.get("ylabel", "Y轴"))
    # 显示右上角的图例，用于区分不同数据系列
    plt.legend()
    # 自动调整边距，让图表元素不会被裁剪
    plt.tight_layout()
    # 将绘制好的图表保存为 PNG 图片
    plt.savefig(save_path, dpi=144, bbox_inches="tight")
    # 关闭当前图表窗口
    plt.close()
    # 返回图像的保存路径，方便后续报告引用
    return save_path

# 提示词前缀
PROMPT_TEMPLATE = '''
你扮演“数据分析助理”。你只能对注入的 Pandas DataFrame `df` 进行分析。
- 如需派生请使用副本（例如 `tmp = df.copy()`）。
- 除了源数据的字段名、数据内容外，所有描述内容均使用中文作答。
- 最终仅返回**一个合法 JSON**，不可有额外文本或符号（包括但不限于```）。


【统一返回 JSON 结构】
{
  "type": "chart_data" | "answer" | "error",
  "input": <简述用户的需求>,
  "data": <根据 type 的载荷>,
}

【各 type 的 data 结构】
- type="answer":
  "data": {"answer": "<先写1行小标题总结，再给要点式答案；包含关键口径/数值>"} 

- type="chart_data":
  "data": {
    "chart_type": "line|bar|scatter",
    "x": ["x轴值1", "x轴值2", ...],
    "y_series": {
      "系列名1": [y值1, y值2, ...],
      "系列名2": [y值1, y值2, ...]
    },
    "summary": "<生成数据分析报告，以及对可视化图的中文解读，不能包含占位符>",
    "title": "<图表标题>",
    "xlabel": "<X轴标题>",
    "ylabel": "<Y轴标题>"
    }
}
  规则：
  * 最多返回 100 行；超过时按与问题最相关的排序截断，并在 warnings 说明“已截断为100行”。
  * 将生成的表格导出到"export_paths"中的目录中
  * summary 中不能出现占位符。

- type="error":
  "data": {
    "message": "<错误原因：缺失字段/筛选不合法/无数据/不确定等>",
    "missing_columns": ["<列名>", "..."],
    "invalid_filters": {"列名": "提供的值"},
    "suggestions": ["<如何改写查询/替代列/放宽筛选>", "..."]
  }

【图表自动选择（当用户未指定）】
- 有时间字段 + 序列 → "line"
- 类别字段 + 聚合值 → "bar"
- 两个连续数值字段 → "scatter"
- 其余无法判断 → 返回 type="error"，说明原因并给出建议

【JSON 规范】
- 仅双引号；不得出现 NaN/Infinity（请转为 null 或实际数值）
- 所有列名必须存在于 df（若使用映射，请先在说明中给出映射关系）
- 仅返回一个 JSON；不要附加解释性文字'''

def data_analyze_agent(csv_path, user_query, api_key=""):
    model = ChatOpenAI(
        api_key=api_key,
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        model_kwargs={'response_format': {'type': 'json_object'}}
    )
    df = pd.read_csv(csv_path)
    agent = create_pandas_dataframe_agent(
        llm=model,
        df=df,
        agent_type="tool-calling",
        allow_dangerous_code=True,
    )
    raw = agent.invoke({"input": PROMPT_TEMPLATE + user_query})
    answer = json.loads(raw.get('output', {}))
    chart_paths = draw_chart(answer.get('data', {}))
    answer['chart_paths'] = chart_paths
    return answer


REPORT_PROMPT = """
你是一名资深数据分析报告专家。你的任务是：  
根据用户传入的 **json 列表**（每个元素包含数据分析结果），将信息汇总并撰写成一份 **结构化报告**。  

【输入说明】  
- 输入是一个由多个 json 组成的列表；  
- 每个 json 至少包含：  
  - type：数据类型（例如 chart、table）  
  - input：用户任务描述  
  - data：包含 summary、指标、分析结论等  
  - chart_paths：图表文件路径（可选）  
  - export_paths：导出的数据表路径（可选）  

【输出要求】  
输出必须是一个 JSON 对象，严格符合以下结构：  
{{
    "subject": "<报告的总标题>",  
    "content_html": "<报告的完整HTML内容>", 
    "attachments": ["<附件地址1>", "<附件地址2>", ...]
}}

【content_html 生成规则】  
必须严格按照以下 HTML 层次生成：  

<h1> [总标题] </h1>

<h2> [小标题] </h2>  
<p> [内容概括，来自该 json 的 summary] </p>  

<h3>数据标题1</h3>  
<table>
  <tbody>
    [逐行列出核心指标及其数值]
  </tbody>
</table>  

<h3>数据标题2</h3>  
<table>
  <tbody>
    [逐行列出核心指标及其数值]
  </tbody>
</table>  

<h3>分析结论</h3>  
<p>[简明总结趋势、问题与亮点]</p>  

<h3>附件</h3>  
<p>[列出该 json 对应的 chart_paths 和 export_paths]</p>  

【参考示例】  
输入 json：  
{{
 'type': 'chart_data',
 'input': '给出全月规模与转化概况，按月汇总PV/UV/Trial/Add/Pay/Refunds，生成核心漏斗图表',
 'data': {{'chart_type': 'bar',
  'x': ['UV访问', '试用申请', '加入购物车', '完成购买', '退款'],
  'y_series': {{'用户数量': [237082, 103784, 25589, 12535, 381]}},
  'summary': '2024年6月核心转化漏斗分析报告：本月总PV为359,167次，UV为237,082人。从UV到试用的转化率为43.78%，试用到加入购物车的转化率为24.66%，购物车到购买的转化率为48.99%，退款率为3.04%。整体转化漏斗呈现典型递减趋势，试用阶段转化率较高，但购物车到购买环节存在较大流失。建议优化购物车体验和支付流程，提升最终转化率。',
  'title': '2024年6月核心转化漏斗',
  'xlabel': '转化阶段',
  'ylabel': '用户数量'}},
 'chart_paths': 'artifacts/2024年6月核心转化漏斗.png'
}}  

输出示例（content_html）：  
<h1>2024年6月数据分析报告</h1>  

<h2>核心转化漏斗分析</h2>  
<p>2024年6月平台总PV为359,167，UV为237,082，用户在试用、加购、购买及退款环节逐级递减。</p>  

<h3>核心数据</h3>  
<table>
  <tbody>
    <tr><th>试用用户数</th><td>103784</td></tr>
    <tr><th>加购用户数</th><td>25589</td></tr>
    <tr><th>购买用户数</th><td>12535</td></tr>
    <tr><th>退款用户数</th><td>381</td></tr>
  </tbody>
</table>  

<h3>转化率表现</h3>  
<table>
  <tbody>
    <tr><th>UV/PV</th><td>65.98%</td></tr>
    <tr><th>试用/UV</th><td>43.77%</td></tr>
    <tr><th>加购/试用</th><td>24.66%</td></tr>
    <tr><th>购买/加购</th><td>48.99%</td></tr>
    <tr><th>退款/购买</th><td>3.04%</td></tr>
  </tbody>
</table>  

<h3>分析结论</h3>  
<p>整体转化链路表现良好，加购到购买环节效率较高，退款率较低，表明转化质量较佳。</p>  

<h3>附件</h3>  
<p>artifacts/funnel_chart.png，outputTable/monthly_funnel_data.csv</p>  

【注意事项】  
- 每个 json 对应一个 <h2> 小节；  
- 所有表格必须使用 <table> 标签；  
- 内容要专业、简洁、结构清晰；  
- 输出的 JSON 必须严格符合规定的键名和层次。  
"""


def generate_report(analysis_log, api_key=""):
    import os
    from langchain_core.prompts import ChatPromptTemplate
    llm = ChatOpenAI(
        api_key=api_key,
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        model_kwargs={'response_format': {'type': 'json_object'}},
    )
    report_prompt = ChatPromptTemplate.from_messages([
        ("system", REPORT_PROMPT),
        ("user", "输入的 json 列表如下：{json_list}请生成报告。")
    ])
    pmt = report_prompt.invoke({"json_list": analysis_log})
    ret = llm.invoke(pmt)
    data = json.loads(ret.content)
    return data


def send_email(sender_email, auth_code, receiver_email, data):
    import zmail
    server = zmail.server(sender_email, auth_code)
    server.send_mail(receiver_email, data)
    return True