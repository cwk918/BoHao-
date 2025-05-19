import streamlit as st
import pandas as pd
import re
import sqlite3
from datetime import datetime
from streamlit_modal import Modal
from contextlib import closing
import os

# 数据库配置
员工='李保德'
DATABASE = f"./datas/客户管理_{员工}.db"

def init_db():
    """初始化数据库"""
    with closing(sqlite3.connect(DATABASE)) as conn:
        c = conn.cursor()
        c.execute(f'''CREATE TABLE IF NOT EXISTS {员工}
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      公司名称 TEXT, 
                      法定代表人 TEXT,
                      有效手机号 TEXT,
                      status TEXT,
                      time TEXT,
                      call_result TEXT)''')
        conn.commit()

init_db()

def get_connection():
    """获取数据库连接"""
    return sqlite3.connect(DATABASE)

# 标准字段顺序
COLUMN_ORDER = ["公司名称", "法定代表人", "有效手机号", "status", "time", "call_result"]

def init_session_state():
    """初始化会话状态并加载数据库数据"""
    base_states = ["current_page", "dialed_page", "unconnected_page"]
    for state in base_states:
        if state not in st.session_state:
            st.session_state[state] = 1

    with get_connection() as conn:
        # 加载未联系客户
        current = pd.read_sql(f"SELECT * FROM {员工} WHERE status='未联系'", conn).to_dict('records')
        # 加载已联系客户
        dialed = pd.read_sql(f"SELECT * FROM {员工} WHERE status='已接通'", conn).to_dict('records')
        # 加载未接通客户
        unconnected = pd.read_sql(f"SELECT * FROM {员工} WHERE status='未接通'", conn).to_dict('records')
    
    st.session_state.current_list = current
    st.session_state.dialed_list = dialed
    st.session_state.unconnected_list = unconnected

init_session_state()

def show_modal(entry):
    modal = Modal("通话备注", key="modal")
    open_modal = st.button("✅ 已联系", key=f"dial_{hash(f'{entry['公司名称']}_{entry['有效手机号']}')}")
    if open_modal:
        modal.open()

    if modal.is_open():
        with modal.container():
            options = ["客户忙，稍后联系", "客户有意向", "客户无意向", "自定义备注"]
            selected_option = st.selectbox("选择通话结果", options)
            custom_note = st.text_input("请输入备注") if selected_option == "自定义备注" else selected_option

            if st.button("保存"):
                with get_connection() as conn:
                    c = conn.cursor()
                    c.execute(f'''UPDATE {员工} SET 
                              status=?,
                              time=?,
                              call_result=?
                              WHERE id=?''',
                              ("已接通", 
                               datetime.now().strftime('%m-%d %H:%M'),
                               custom_note,
                               entry['id']))
                    conn.commit()
                init_session_state()  # 刷新数据
                modal.close()
                st.rerun()

def process_uploaded_file(uploaded_file):
    """处理上传文件并生成待确认数据"""
    try:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
        df = df[df['有效手机号'] != '-']
        required_cols = {"公司": "公司名称", "法定代表人": "法定代表人", "有效手机号": "有效手机号"}

        df.columns = df.columns.str.replace(r'公司|名称', '公司').str.replace(r'法定代表人', '法定代表人')
        df = df.rename(columns={col: required_cols[col] for col in required_cols if col in df.columns})

        df['有效手机号'] = df['有效手机号'].astype(str).apply(lambda x: re.findall(r'\d{8,}', x))
        grouped = df.explode('有效手机号').groupby(['公司名称', '法定代表人']).agg({'有效手机号': lambda x: ', '.join(x)}).reset_index()

        new_entries = [{
            "公司名称": row['公司名称'],
            "法定代表人": row['法定代表人'],
            "有效手机号": row['有效手机号'],
            "status": "未联系",
            "time": None,
            "call_result": None
        } for _, row in grouped.iterrows()]

        st.session_state.parsed_data = new_entries
        st.success(f"发现 {len(new_entries)} 条待确认记录")
        return True
    except Exception as e:
        st.error(f"文件解析错误: {str(e)}")
        return False

def confirm_import():
    """执行数据导入并去重"""
    if st.session_state.parsed_data:
        with get_connection() as conn:
            c = conn.cursor()
            existing_phones = [x[0] for x in c.execute(f"SELECT 有效手机号 FROM {员工}").fetchall()]
            new_entries = [x for x in st.session_state.parsed_data if x['有效手机号'] not in existing_phones]

            for entry in new_entries:
                c.execute(f'''INSERT INTO {员工} 
                          (公司名称, 法定代表人, 有效手机号, status, time, call_result)
                          VALUES (?, ?, ?, ?, ?, ?)''',
                          (entry['公司名称'], entry['法定代表人'], entry['有效手机号'],
                           '未联系', None, None))
            conn.commit()
            
            st.session_state.parsed_data = None
            init_session_state()  # 刷新数据
            st.toast(f"成功导入 {len(new_entries)} 条新记录", icon="✅")
def mark_as_connected(index):
    entry = st.session_state.current_list[index]
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(f'''UPDATE {员工} SET 
                  status=?,
                  time=?,
                  call_result=?
                  WHERE id=?''',
                  ('已接通',
                   datetime.now().strftime('%m-%d %H:%M'),
                   '已接通',
                   entry['id']))
        conn.commit()
    init_session_state()
    
def mark_as_unconnected(index):
    entry = st.session_state.current_list[index]
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(f'''UPDATE {员工} SET 
                  status=?,
                  time=?,
                  call_result=?
                  WHERE id=?''',
                  ('未接通',
                   datetime.now().strftime('%m-%d %H:%M'),
                   '未接通',
                   entry['id']))
        conn.commit()
    init_session_state()
    # st.rerun()

def clear_table_data():
    """清空数据库数据"""
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(f"DELETE FROM {员工}")
        conn.commit()
    init_session_state()
    st.toast("数据库数据已清空", icon="✅")

# 界面部分保持不变...
# 当员工选择改变时，重新初始化会话状态
def on_employee_selection_change():
    init_session_state()
st.title("🏢 企业客户管理系统")
# st.header(f'当前员工:{selected_employee}')
with st.expander("📤 数据导入", expanded=True):
    uploaded_file = st.file_uploader(
        "上传客户表(Excel/CSV)",
        type=["xlsx", "csv"],
        help="需含公司名称、法定代表人、有效手机号三列"
    )

    if uploaded_file and process_uploaded_file(uploaded_file):
        st.button(
            "🚀 确认导入",
            on_click=confirm_import,
            help="去重后存入系统"
        )
        with st.container(border=True):
            st.dataframe(pd.DataFrame(st.session_state.parsed_data[:5]), hide_index=True)


tab1, tab2, tab3, tab4 = st.tabs(["待联系客户", "已联系记录", "未接通记录", "统计信息"])

# 示例修改后的分页查询（在tab1中）：
with tab1:
    if not st.session_state.current_list:
        st.info("👆 请先上传并导入企业客户表")
    else:
        st.subheader(f"待联系客户（共 {len(st.session_state.current_list)} 家）")

    items_per_page = 20
    start_idx = (st.session_state.current_page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    current_page_list = st.session_state.current_list[start_idx:end_idx]

    for i, entry in enumerate(current_page_list):
        unique_key = hash(f"{entry['公司名称']}_{entry['有效手机号']}")

        with st.container(border=True):
            col_left, col_right = st.columns([5, 2])

            with col_left:
                phone_links = []
                phones = entry['有效手机号'].split(', ')
                for phone in phones:
                    phone_links.append(f'📞 电话‌: <a href="tel:{phone}" style="text-decoration:none;">{phone}</a>')
                phone_html = '<br>'.join(phone_links)
                st.markdown(f"""
                &zwnj;**🏭 公司名称**&zwnj;: {entry['公司名称']}  
                &zwnj;**👤 法定代表人**&zwnj;: {entry['法定代表人']}  
                {phone_html}
                """, unsafe_allow_html=True)

            with col_right:
                actual_index = next(
                    (idx for idx, item in enumerate(st.session_state.current_list)
                    if item['有效手机号'] == entry['有效手机号']),
                    None
                )
                if actual_index is not None:
                    # show_modal(entry)
                    st.button(
                        "✅ 已接通",
                        key=f"connected_{unique_key}",
                        on_click=mark_as_connected,
                        args=(actual_index,),
                        help="标记该客户已接通"
                    )
                    st.button(
                        "❌ 未接通",
                        key=f"unconnected_{unique_key}",
                        on_click=mark_as_unconnected,
                        args=(actual_index,),
                        help="标记该客户未接通"
                    )

    # 分页导航
    total_pages = len(st.session_state.current_list) // items_per_page + (1 if len(st.session_state.current_list) % items_per_page != 0 else 0)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.session_state.current_page > 1:
            st.button("上一页", on_click=lambda: st.session_state.update(current_page=st.session_state.current_page - 1))
    with col2:
        st.write(f"第 {st.session_state.current_page} 页，共 {total_pages} 页")
    with col3:
        if st.session_state.current_page < total_pages:
            st.button("下一页", on_click=lambda: st.session_state.update(current_page=st.session_state.current_page + 1))

with tab2:
    if st.session_state.dialed_list:
        st.subheader(f"已接通记录（共 {len(st.session_state.dialed_list)} 家）")
        items_per_page = 20
        start_idx = (st.session_state.dialed_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_page_list = st.session_state.dialed_list[start_idx:end_idx]

        for entry in current_page_list:
            with st.container(border=True):
                phone_links = []
                phones = entry['有效手机号'].split(', ')
                for phone in phones:
                    phone_links.append(f'📞 电话‌: {phone}')
                phone_html = '<br>'.join(phone_links)
                st.markdown(f"""
                ~~🏭 公司名称~~: {entry['公司名称']}  
                ~~👤 法定代表人~~: {entry['法定代表人']}  
                {phone_html}
                &zwnj;**🕒 联系时间**&zwnj;: {entry['time']}
                &zwnj;**📞 通话结果**&zwnj;: {entry['call_result']}
                """, unsafe_allow_html=True)

        # 分页导航
        total_pages = len(st.session_state.dialed_list) // items_per_page + (1 if len(st.session_state.dialed_list) % items_per_page != 0 else 0)
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.session_state.dialed_page > 1:
                st.button("上一页", on_click=lambda: st.session_state.update(dialed_page=st.session_state.dialed_page - 1))
        with col2:
            st.write(f"第 {st.session_state.dialed_page} 页，共 {total_pages} 页")
        with col3:
            if st.session_state.dialed_page < total_pages:
                st.button("下一页", on_click=lambda: st.session_state.update(dialed_page=st.session_state.dialed_page + 1))
    else:
        st.info("尚未标记任何已联系客户")

with tab3:
    if st.session_state.unconnected_list:
        st.subheader(f"未接通记录（共 {len(st.session_state.unconnected_list)} 家）")
        items_per_page = 20
        start_idx = (st.session_state.unconnected_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        current_page_list = st.session_state.unconnected_list[start_idx:end_idx]

        for entry in current_page_list:
            with st.container(border=True):
                phone_links = []
                phones = entry['有效手机号'].split(', ')
                for phone in phones:
                    phone_links.append(f'📞 电话‌: {phone}')
                phone_html = '<br>'.join(phone_links)
                st.markdown(f"""
                ~~🏭 公司名称~~: {entry['公司名称']}  
                ~~👤 法定代表人~~: {entry['法定代表人']}  
                {phone_html}
                &zwnj;**🕒 联系时间**&zwnj;: {entry['time']}
                &zwnj;**📞 通话结果**&zwnj;: {entry['call_result']}
                """, unsafe_allow_html=True)

        # 分页导航
        total_pages = len(st.session_state.unconnected_list) // items_per_page + (1 if len(st.session_state.unconnected_list) % items_per_page != 0 else 0)
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            if st.session_state.unconnected_page > 1:
                st.button("上一页", on_click=lambda: st.session_state.update(unconnected_page=st.session_state.unconnected_page - 1))
        with col2:
            st.write(f"第 {st.session_state.unconnected_page} 页，共 {total_pages} 页")
        with col3:
            if st.session_state.unconnected_page < total_pages:
                st.button("下一页", on_click=lambda: st.session_state.update(unconnected_page=st.session_state.unconnected_page + 1))
    else:
        st.info("尚未标记任何未接通客户")

# 导出数据修改
with st.sidebar:
    if st.button("导出完整数据库"):
        # 直接读取数据库文件二进制内容
        with open(DATABASE, "rb") as f:  
            db_data = f.read()
        
        st.download_button(
            label="下载数据库",
            data=db_data,
            file_name=f"客户管理_{员工}.db",
            mime="application/vnd.sqlite3"
        )
    
    st.button("🗑️清空数据", on_click=clear_table_data)

    # 新增上传db文件功能
    uploaded_db_file = st.file_uploader("上传数据库文件 (.db)", type=["db"])
    if uploaded_db_file is not None:
        # 创建保存数据库文件的目录
        if not os.path.exists("./datas"):
            os.makedirs("./datas")

        # 保存上传的数据库文件
        with open(DATABASE, "wb") as f:
            f.write(uploaded_db_file.getbuffer())
        st.success("数据库文件上传成功！请刷新页面查看更新后的数据。")



# 统计信息修改
with tab4:
    with get_connection() as conn:
        total_calls = pd.read_sql(f"SELECT COUNT(*) FROM {员工} WHERE status IN ('已接通', '未接通')", conn).iloc[0,0]
        connected_calls = pd.read_sql(f"SELECT COUNT(*) FROM {员工} WHERE status='已接通'", conn).iloc[0,0]
        unconnected_calls = pd.read_sql(f"SELECT COUNT(*) FROM {员工} WHERE status='未接通'", conn).iloc[0,0]

    st.subheader("统计信息")
    st.write(f"总计拨打电话: {total_calls} 家")
    st.write(f"已接通电话: {connected_calls} 家")
    st.write(f"未接通电话: {unconnected_calls} 家")
