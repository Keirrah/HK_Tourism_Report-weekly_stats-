# dashboard.py
"""
香港出入境流量数据可视化面板 (Dashboard)
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import datetime
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------
# 1. 页面设置与高质感 CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Hong Kong Tourism Dashboard",
    page_icon="🇭🇰",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from download_data import fetch_latest_immd_data, DEFAULT_FILE_NAME
from weekly_report_data import (
    load_data, 
    calculate_port_totals, 
    apply_mapping, 
    merge_other, 
    merge_current_previous, 
    calculate_metrics, 
    sort_report, 
    add_total
)

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
    }
    /* 表格高质感样式 */
    .report-table {
        width: 100%;
        border-collapse: collapse;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        font-size: 13px;
        background-color: #ffffff;
        margin-top: 10px;
    }
    .report-table th {
        background-color: #1E5631;
        color: white;
        padding: 10px;
        text-align: right;
        font-weight: 600;
    }
    .report-table th:nth-child(1), .report-table th:nth-child(2) { text-align: left; }
    .report-table td {
        padding: 8px 10px;
        border-bottom: 1px solid #e9ecef;
        text-align: right;
    }
    .report-table td:nth-child(1), .report-table td:nth-child(2) { text-align: left; }
    .report-table tr:hover { background-color: #f1f3f5; }
    /* Grand Total 专属醒目高亮底色 */
    .report-table .total-row { 
        font-weight: bold; 
        background-color: #e8f5e9 !important;
        border-top: 2px solid #1E5631;
        border-bottom: 2px solid #1E5631;
    }
    .wow-up { color: #0056b3; font-weight: bold; }
    .wow-down { color: #d9534f; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# 2. 侧边栏与数据控制中心
# ---------------------------------------------------------
st.sidebar.title("🎛️ Sidebar")

if st.sidebar.button("⏬ Update to the latest data", use_container_width=True):
    with st.spinner("Downloading from data.gov.hk..."):
        try:
            fetch_latest_immd_data()
            st.sidebar.success("✅ Success!")
            st.cache_data.clear()
        except Exception as e:
            st.sidebar.error(f"❌ Download failed: {e}")

if st.sidebar.button("🔄 Refresh panel data", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")

@st.cache_data(ttl=3600)
def get_raw_data():
    return load_data()

try:
    df_raw = get_raw_data()
except Exception as e:
    st.error(f"Data loading failed: {e}")
    st.stop()


# ---------------------------------------------------------
# 3. 容错切周逻辑 (支持周中 Partial Week 运行)
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def get_processed_weeks(df):
    df_dates = pd.DataFrame({"Date": df["Date"].unique()}).sort_values("Date")
    df_dates["Week_Start"] = df_dates["Date"].apply(lambda d: d - pd.Timedelta(days=d.weekday()))
    df_dates["Week_End"] = df_dates["Week_Start"] + pd.Timedelta(days=6)
    
    week_stats = df_dates.groupby(["Week_Start", "Week_End"])["Date"].agg(["min", "max", "count"]).reset_index()
    week_stats = week_stats.rename(columns={"count": "Days_Count", "min": "Actual_Min", "max": "Actual_Max"})
    week_stats = week_stats.sort_values("Week_Start", ascending=False).reset_index(drop=True)
    week_stats["Is_Complete"] = week_stats["Days_Count"] == 7
    return week_stats

week_stats = get_processed_weeks(df_raw)

week_options = []
for _, row in week_stats.iterrows():
    s_str = row['Week_Start'].strftime('%Y-%m-%d')
    e_str = row['Week_End'].strftime('%Y-%m-%d')
    if row["Is_Complete"]:
        status = "Full Week (7 days)"
    else:
        status = f"Partial Week ( {row['Days_Count']} days: ~{row['Actual_Max'].strftime('%m/%d')})"
    week_options.append(f"{s_str} ~ {e_str} [{status}]")

# 默认定位到最新出现的周
st.sidebar.subheader("📅 Analysis Period Selection")
selected_base_week_str = st.sidebar.selectbox("Select Base Week (Current Week):", week_options, index=0)

base_idx = week_options.index(selected_base_week_str)
base_row = week_stats.iloc[base_idx]
base_start = base_row['Week_Start']
base_end = base_row['Actual_Max']  # 截取到实际最大出现日期

default_comp_idx = min(base_idx + 1, len(week_options) - 1)
selected_comp_week_str = st.sidebar.selectbox("Select Comparison Week:", week_options, index=default_comp_idx)
comp_idx = week_options.index(selected_comp_week_str)
comp_row = week_stats.iloc[comp_idx]
comp_start = comp_row['Week_Start']

# 核心 WTD 对齐机制：对比周裁剪出相同的天数
base_days_count = base_row['Days_Count']
comp_cutoff_date = comp_start + pd.Timedelta(days=base_days_count - 1)

base_df = df_raw[(df_raw["Date"] >= base_start) & (df_raw["Date"] <= base_end)].copy()
comp_df = df_raw[(df_raw["Date"] >= comp_start) & (df_raw["Date"] <= comp_cutoff_date)].copy()


# ---------------------------------------------------------
# 4. 核心 KPI 汇总卡片
# ---------------------------------------------------------
st.title("🇭🇰 Hong Kong Tourism Dashboard")

if base_days_count < 7:
    st.info(f"💡 **WTD Mode**: The current base week only includes the first **{base_days_count}** days ( {base_start.strftime('%m/%d')} ~ {base_end.strftime('%m/%d')} ). The comparison week has been automatically trimmed to the same period ( {comp_start.strftime('%m/%d')} ~ {comp_cutoff_date.strftime('%m/%d')} ) for fair Apple-to-Apple comparison!")
else:
    st.caption(f"Base Week: {base_start.strftime('%Y-%m-%d')} ~ {base_end.strftime('%Y-%m-%d')} | Comparison Week: {comp_start.strftime('%Y-%m-%d')} ~ {comp_cutoff_date.strftime('%Y-%m-%d')}")

mainland_base = base_df[base_df["Arrival / Departure"] == "Arrival"]["Mainland Visitors"].sum()
mainland_comp = comp_df[comp_df["Arrival / Departure"] == "Arrival"]["Mainland Visitors"].sum()
mainland_wow = ((mainland_base - mainland_comp) / mainland_comp * 100) if mainland_comp > 0 else 0

local_base = base_df[base_df["Arrival / Departure"] == "Departure"]["Hong Kong Residents"].sum()
local_comp = comp_df[comp_df["Arrival / Departure"] == "Departure"]["Hong Kong Residents"].sum()
local_wow = ((local_base - local_comp) / local_comp * 100) if local_comp > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric(f"Mainland Arrival ({base_days_count} days)", f"{mainland_base:,.0f}", f"{mainland_wow:+.1f}% vs Comparison Week")
col2.metric(f"Local Departure ({base_days_count} days)", f"{local_base:,.0f}", f"{local_wow:+.1f}% vs Comparison Week")
col3.metric("Mainland Arrival (Comparison Week)", f"{mainland_comp:,.0f}")
col4.metric("Local Departure (Comparison Week)", f"{local_comp:,.0f}")

st.markdown("---")


# ---------------------------------------------------------
# 5. 每日对比柱形图 (Mainland Arrival + Local Departure)
# ---------------------------------------------------------
st.subheader("🗓️ Daily Comparison within the Weeks")

def get_daily_trend(df_sub, label):
    arr = df_sub[df_sub["Arrival / Departure"] == "Arrival"].groupby("Date")["Mainland Visitors"].sum().reset_index()
    dep = df_sub[df_sub["Arrival / Departure"] == "Departure"].groupby("Date")["Hong Kong Residents"].sum().reset_index()
    merged = pd.merge(arr, dep, on="Date")
    merged["DayOfWeek"] = merged["Date"].dt.dayofweek
    merged["Period"] = label
    return merged

df_base_daily = get_daily_trend(base_df, "Base Week")
df_comp_daily = get_daily_trend(comp_df, "Comparison Week")
df_overlay = pd.concat([df_base_daily, df_comp_daily]).sort_values("DayOfWeek")

day_map = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri', 5: 'Sat', 6: 'Sun'}
df_overlay['DayLabel'] = df_overlay['DayOfWeek'].map(day_map)

# 精简数值标签 (千 / k)
df_overlay['Mainland_Label'] = df_overlay['Mainland Visitors'].apply(lambda x: f"{x/1000:.1f}k" if x >= 1000 else f"{x:.0f}")
df_overlay['Local_Label'] = df_overlay['Hong Kong Residents'].apply(lambda x: f"{x/1000:.1f}k" if x >= 1000 else f"{x:.0f}")

# 图表 1: Mainland Arrival Daily Comparison
fig_mainland = px.bar(
    df_overlay, 
    x="DayLabel", 
    y="Mainland Visitors", 
    color="Period", 
    barmode="group",
    text="Mainland_Label",
    title=" Mainland Arrival Daily Comparison (Base Week vs Comparison Week)",
    color_discrete_map={"Base Week": "#1E5631", "Comparison Week": "#A2C4C9"},
    labels={"DayLabel": "Day", "Mainland Visitors": "Passengers", "Period": "Time"}
)
fig_mainland.update_traces(textposition='outside')
fig_mainland.update_layout(height=380, hovermode="x unified", yaxis_title="人次")
st.plotly_chart(fig_mainland, use_container_width=True)

# 图表 2: Local Departure Daily Comparison
fig_local = px.bar(
    df_overlay, 
    x="DayLabel", 
    y="Hong Kong Residents", 
    color="Period", 
    barmode="group",
    text="Local_Label",
    title=" Local Departure Daily Comparison (Base Week vs Comparison Week)",
    color_discrete_map={"Base Week": "#2B5B84", "Comparison Week": "#90B4CE"},
    labels={"DayLabel": "Day", "Hong Kong Residents": "Passengers", "Period": "Time"}
)
fig_local.update_traces(textposition='outside')
fig_local.update_layout(height=380, hovermode="x unified", yaxis_title="人次")
st.plotly_chart(fig_local, use_container_width=True)


# ---------------------------------------------------------
# 6. 股票级全历史趋势折线图
# ---------------------------------------------------------
st.subheader("📈 Full Historical Daily Traffic Trends")

df_all_arr = df_raw[df_raw["Arrival / Departure"] == "Arrival"].groupby("Date")["Mainland Visitors"].sum().reset_index()
df_all_dep = df_raw[df_raw["Arrival / Departure"] == "Departure"].groupby("Date")["Hong Kong Residents"].sum().reset_index()
df_macro = pd.merge(df_all_arr, df_all_dep, on="Date").sort_values("Date")

fig_macro = px.line(
    df_macro, 
    x="Date", 
    y=["Mainland Visitors", "Hong Kong Residents"],
    title="Full Historical Daily Traffic Trends",
    color_discrete_map={"Mainland Visitors": "#1E5631", "Hong Kong Residents": "#2B5B84"},
    labels={"value": "Passengers", "variable": "Traffic Type", "Date": "Date"}
)
fig_macro.update_xaxes(
    rangeslider_visible=True,
    rangeselector=dict(
        buttons=list([
            dict(count=1, label="1 month", step="month", stepmode="backward"),
            dict(count=6, label="6 months", step="month", stepmode="backward"),
            dict(count=1, label="1 year", step="year", stepmode="backward"),
            dict(step="all", label="Full History")
        ])
    )
)
fig_macro.update_layout(height=480, hovermode="x unified")
st.plotly_chart(fig_macro, use_container_width=True)


# ---------------------------------------------------------
# 7. 数据表格 (带日期区间说明 + Grand Total 特殊高亮底色)
# ---------------------------------------------------------
st.subheader("📋 Weekly Report Data Verification Table")

current_p = calculate_port_totals(base_df)
previous_p = calculate_port_totals(comp_df)

current_p = apply_mapping(current_p)
previous_p = apply_mapping(previous_p)

current_p = merge_other(current_p)
previous_p = merge_other(previous_p)

report_df = merge_current_previous(current_p, previous_p)
report_df = calculate_metrics(report_df)
report_df = sort_report(report_df)
report_df = add_total(report_df)

# 构建带日期与 HTML/CSS 箭头的自定义数据表格
# 构建带日期与 HTML/CSS 箭头的自定义数据表格
def render_custom_table(df, b_start, b_end, c_start, c_end):
    base_date_str = f"{b_start.strftime('%d/%m/%Y')} - {b_end.strftime('%d/%m/%Y')}"
    comp_date_str = f"{c_start.strftime('%d/%m/%Y')} - {c_end.strftime('%d/%m/%Y')}"

    html_code = f"""
    <div style="margin-bottom: 8px; font-weight: bold; color: #1E5631;">
        📅 Base Period: <span style="color:#000;">{base_date_str}</span> | 
        Comparison Period (Audit): <span style="color:#000;">{comp_date_str}</span>
    </div>
    <table class="report-table">
        <thead>
            <tr>
    """
    headers = ["Group", "Display Name", "Mainland Arrivals", "Arrival Share", "Arrival WoW %", "Local Departures", "Departure Share", "Departure WoW %"]
    for h in headers:
        html_code += f'<th>{h}</th>'
    html_code += '</tr></thead><tbody>'

    for idx, row in df.iterrows():
        is_total = row["Group"] in ["Grand Total", "Total"]
        tr_class = ' class="total-row"' if is_total else ''
        html_code += f'<tr{tr_class}>'
        
        # Group & Name
        html_code += f'<td>{row["Group"]}</td><td>{row["Display Name"]}</td>'
        
        # Mainland Arrivals
        arr_val = f"{row['Mainland Arrivals']:,.0f}" if pd.notnull(row['Mainland Arrivals']) else "-"
        html_code += f'<td>{arr_val}</td>'
        
        # Share
        arr_share = f"{row['Arrival Share']:.1%}" if pd.notnull(row['Arrival Share']) and not np.isnan(row['Arrival Share']) else "-"
        html_code += f'<td>{arr_share}</td>'
        
        # Arrival WoW (仅保留箭头 + 绝对值百分比)
        arr_wow_val = row['Arrival WoW %']
        if pd.notnull(arr_wow_val) and not np.isnan(arr_wow_val):
            if arr_wow_val > 0:
                arr_wow_html = f'<span class="wow-up">↑ {abs(arr_wow_val):.1%}</span>'
            elif arr_wow_val < 0:
                arr_wow_html = f'<span class="wow-down">↓ {abs(arr_wow_val):.1%}</span>'
            else:
                arr_wow_html = f'{arr_wow_val:.1%}'
        else:
            arr_wow_html = "-"
        html_code += f'<td>{arr_wow_html}</td>'
        
        # Local Departures
        dep_val = f"{row['Local Departures']:,.0f}" if pd.notnull(row['Local Departures']) else "-"
        html_code += f'<td>{dep_val}</td>'
        
        # Share
        dep_share = f"{row['Departure Share']:.1%}" if pd.notnull(row['Departure Share']) and not np.isnan(row['Departure Share']) else "-"
        html_code += f'<td>{dep_share}</td>'
        
        # Departure WoW (仅保留箭头 + 绝对值百分比)
        dep_wow_val = row['Departure WoW %']
        if pd.notnull(dep_wow_val) and not np.isnan(dep_wow_val):
            if dep_wow_val > 0:
                dep_wow_html = f'<span class="wow-up">↑ {abs(dep_wow_val):.1%}</span>'
            elif dep_wow_val < 0:
                dep_wow_html = f'<span class="wow-down">↓ {abs(dep_wow_val):.1%}</span>'
            else:
                dep_wow_html = f'{dep_wow_val:.1%}'
        else:
            dep_wow_html = "-"
        html_code += f'<td>{dep_wow_html}</td>'

        html_code += '</tr>'

    html_code += '</tbody></table>'
    return html_code

st.html(render_custom_table(report_df, base_start, base_end, comp_start, comp_cutoff_date))