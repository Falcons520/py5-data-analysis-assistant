import streamlit as st
import os
import io
import pandas as pd
from L15 import data_analyze_agent, generate_report, send_email

# Streamlit Cloud secrets first, fallback to env var
try:
    API_KEY = st.secrets.get("DEEPSEEK_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")
except Exception:
    API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

st.set_page_config(page_title='AI数据分析助手', layout='wide')

st.title('AI数据分析助手')
st.markdown('基于 DeepSeek 模型的智能数据分析与报告生成工具')

with st.sidebar:
    st.header('邮件配置')
    sender_email = st.text_input('发送人邮箱', value='875736154@qq.com')
    auth_code = st.text_input('邮箱授权码', type='password')
    receiver_email = st.text_input('接收人邮箱', value='875736154@qq.com')

uploaded_file = st.file_uploader('上传数据文件', type=['csv', 'xlsx', 'xls', 'json', 'txt', 'tsv'])
if uploaded_file is not None:
    fname = uploaded_file.name.lower()
    if fname.endswith('.xlsx'):
        df = pd.read_excel(uploaded_file, engine='openpyxl')
    elif fname.endswith('.xls'):
        df = pd.read_excel(uploaded_file, engine='xlrd')
    elif fname.endswith('.json'):
        df = pd.read_json(uploaded_file)
    elif fname.endswith('.tsv'):
        df = pd.read_csv(uploaded_file, sep='\t')
    elif fname.endswith('.txt'):
        df = pd.read_csv(uploaded_file, sep=None, engine='python')
    else:
        df = pd.read_csv(uploaded_file)
    st.subheader('数据预览')
    st.dataframe(df.head(5))
    
    user_query = st.text_area('输入分析需求', height=100, placeholder='例如：给出全月规模与转化概况，按月汇总 PV/UV/Trial/Add/Pay/Refunds，生成核心漏斗图表。')
    
    if st.button('开始分析', disabled=not user_query):
        with st.spinner('正在分析数据...'):
            try:
                base_name = os.path.splitext(uploaded_file.name)[0]
                csv_path = os.path.join(os.path.dirname(__file__), base_name + '.csv')
                df.to_csv(csv_path, index=False)
                
                answer = data_analyze_agent(csv_path, user_query, API_KEY)
                
                st.success('数据分析完成！')
                
                if answer.get('chart_paths'):
                    st.subheader('生成的图表')
                    st.image(answer['chart_paths'])
                
                if answer.get('data', {}).get('summary'):
                    st.subheader('分析摘要')
                    st.write(answer['data']['summary'])
                
                analysis_log = [answer]
                
                with st.spinner('正在生成报告...'):
                    report_data = generate_report(analysis_log, API_KEY)
                
                st.subheader('数据分析报告')
                st.markdown(report_data.get('content_html', ''), unsafe_allow_html=True)
                
                if auth_code:
                    if st.button('发送邮件报告'):
                        with st.spinner('正在发送邮件...'):
                            send_email(sender_email, auth_code, receiver_email, report_data)
                            st.success(f'邮件已发送至 {receiver_email}')
                else:
                    st.info('请在侧边栏填写邮箱授权码以发送邮件')
                
            except Exception as e:
                st.error(f'分析失败: {str(e)}')
else:
    st.info('请先上传数据文件（支持CSV、Excel、JSON、TXT、TSV等格式）')