# dashboard.py
"""
香港出入境流量数据可视化面板 (Dashboard)
"""

import sys
import subprocess
from pathlib import Path

# 1. 自动检测并安装 dashboard 所需依赖包
REQUIRED_PACKAGES = ["streamlit", "plotly", "pandas", "numpy"]

for pkg in REQUIRED_PACKAGES:
    try:
        __import__(pkg)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

# 2. 页面全局配置
st.set_page_config(
    page_title="香港出入境流量分析 Dashboard",
    page_icon="📊",
    layout="wide"
)

# 路径设置
BASE_DIR = Path(__file__).resolve().parent
RAW_FILE = BASE_DIR / "input" / "latest_immd_raw.csv"

# =====================================================
# 数据加载与缓存 (Data Loading & Caching)
# =====================================================

@st.cache_data(ttl=3600)
def load_and_clean_raw_data():
    if not RAW_FILE.exists():
        st.error(f"❌ 未找到原始数据文件: {RAW_FILE}。请先运行 download_data.py 下载最新数据！")
        st.stop()
        
    df = pd.read_csv(RAW_FILE)
    df.columns = df.columns.str.strip()
    
    # 兼容多种日期格式
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    
    numeric_cols = ["Hong Kong Residents", "Mainland Visitors", "Other Visitors", "Total"]
    for col in numeric_cols:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(",", "")
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            
    return df

raw_df = load_and_clean_raw_data()
all_control_points = ["全港 Grand Total"] + sorted(raw_df["Control Point"].unique().tolist())

st.title("📊 香港出入境流量追踪 Dashboard")
st.caption("数据来源：香港入境事务处 (data.gov.hk) | 每日数据更新")

tab1, tab2, tab3 = st.tabs([
    "📈 图1：历史流量总趋势", 
    "📅 图2：本周 vs 上周对比", 
    "🗓️ 图3：月度日历看板 (规划中)"
])

# =====================================================
# TAB 1: 历史流量总趋势图 (Graph 1)
# =====================================================

with tab1:
    st.subheader("1. 历史每日出入境流量趋势图")
    
    col1, col2 = st.columns([2, 1])
    with col1:
        selected_port_t1 = st.selectbox("选择口岸 (Control Point):", all_control_points, key="port_t1")
    with col2:
        use_ma7 = st.checkbox("开启 7 天移动平均 (Smooth Line)", value=False)

    if selected_port_t1 == "全港 Grand Total":
        df_t1 = raw_df.groupby(["Date", "Arrival / Departure"])[["Mainland Visitors", "Hong Kong Residents"]].sum().reset_index()
    else:
        df_t1 = raw_df[raw_df["Control Point"] == selected_port_t1].copy()

    arrival_df = df_t1[df_t1["Arrival / Departure"] == "Arrival"].groupby("Date")["Mainland Visitors"].sum().reset_index()
    departure_df = df_t1[df_t1["Arrival / Departure"] == "Departure"].groupby("Date")["Hong Kong Residents"].sum().reset_index()

    merged_t1 = pd.merge(arrival_df, departure_df, on="Date", how="outer").fillna(0).sort_values("Date")
    
    if use_ma7:
        merged_t1["Mainland_Plot"] = merged_t1["Mainland Visitors"].rolling(window=7, min_periods=1).mean()
        merged_t1["Local_Plot"] = merged_t1["Hong Kong Residents"].rolling(window=7, min_periods=1).mean()
        line_title_suffix = " (7日移动平均)"
    else:
        merged_t1["Mainland_Plot"] = merged_t1["Mainland Visitors"]
        merged_t1["Local_Plot"] = merged_t1["Hong Kong Residents"]
        line_title_suffix = " (每日原始值)"

    fig1 = go.Figure()

    fig1.add_trace(go.Scatter(
        x=merged_t1["Date"], 
        y=merged_t1["Mainland_Plot"],
        mode="lines",
        name=f"Mainland Arrivals{line_title_suffix}",
        line=dict(color="#E63946", width=2),
        hovertemplate="日期: %{x|%Y-%m-%d}<br>内地入境人次: %{y:,.0f}<extra></extra>"
    ))

    fig1.add_trace(go.Scatter(
        x=merged_t1["Date"], 
        y=merged_t1["Local_Plot"],
        mode="lines",
        name=f"Local Departures{line_title_suffix}",
        line=dict(color="#1F77B4", width=2),
        hovertemplate="日期: %{x|%Y-%m-%d}<br>港人出境人次: %{y:,.0f}<extra></extra>"
    ))

    min_year = merged_t1["Date"].dt.year.min()
    max_year = merged_t1["Date"].dt.year.max()
    
    for yr in range(min_year, max_year):
        year_end_date = pd.to_datetime(f"{yr}-12-31")
        if year_end_date >= merged_t1["Date"].min() and year_end_date <= merged_t1["Date"].max():
            fig1.add_vline(
                x=year_end_date.timestamp() * 1000, 
                line_width=1, 
                line_dash="dash", 
                line_color="gray"
            )

    fig1.update_layout(
        title=f"<b>[{selected_port_t1}] 全量历史流量趋势</b>",
        xaxis_title="年份",
        yaxis_title="人次 (Person Times)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis=dict(
            dtick="M12", 
            tickformat="%Y", 
            showgrid=True
        )
    )

    st.plotly_chart(fig1, width="stretch")


# =====================================================
# TAB 2: 本周 vs 上周对比图 (Graph 2 - 修复双线同图逻辑)
# =====================================================

with tab2:
    st.subheader("2. 本周 vs 上周流量走势对比")

    col1, col2 = st.columns(2)
    with col1:
        selected_port_t2 = st.selectbox("选择口岸 (Control Point):", all_control_points, key="port_t2")
    with col2:
        flow_type = st.radio("选择流量方向:", ["Mainland Arrivals (内地入境)", "Local Departures (港人出境)"], horizontal=True)

    # 1. 过滤口岸
    if selected_port_t2 == "全港 Grand Total":
        df_t2 = raw_df.copy()
    else:
        df_t2 = raw_df[raw_df["Control Point"] == selected_port_t2].copy()

    # 2. 动态定位本周与上周日期区间 (Mon - Sun)
    max_date = df_t2["Date"].max()
    # 找到最近一个周一
    this_week_start = max_date - pd.Timedelta(days=max_date.weekday())
    this_week_end = this_week_start + pd.Timedelta(days=6)
    
    last_week_start = this_week_start - pd.Timedelta(days=7)
    last_week_end = this_week_start - pd.Timedelta(days=1)

    # 3. 参数匹配
    if "Mainland" in flow_type:
        dir_filter = "Arrival"
        metric_col = "Mainland Visitors"
        color_this_week = "#E63946"
        color_last_week = "#FFA6A8"
        target_title = "Mainland Arrivals (内地入境)"
    else:
        dir_filter = "Departure"
        metric_col = "Hong Kong Residents"
        color_this_week = "#1F77B4"
        color_last_week = "#A0C4FF"
        target_title = "Local Departures (港人出境)"

    # 4. 按方向切片与汇总
    filtered_df = df_t2[df_t2["Arrival / Departure"] == dir_filter]

    # 构建统一的 Monday -> Sunday 标尺框架
    week_template = pd.DataFrame({
        "DayNum": list(range(7)),
        "DayName": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    })

    # 本周数据提取与映射
    tw_data = filtered_df[(filtered_df["Date"] >= this_week_start) & (filtered_df["Date"] <= this_week_end)]
    tw_grouped = tw_data.groupby("Date")[metric_col].sum().reset_index()
    tw_grouped["DayNum"] = tw_grouped["Date"].dt.weekday
    tw_final = pd.merge(week_template, tw_grouped, on="DayNum", how="left")

    # 上周数据提取与映射
    lw_data = filtered_df[(filtered_df["Date"] >= last_week_start) & (filtered_df["Date"] <= last_week_end)]
    lw_grouped = lw_data.groupby("Date")[metric_col].sum().reset_index()
    lw_grouped["DayNum"] = lw_grouped["Date"].dt.weekday
    lw_final = pd.merge(week_template, lw_grouped, on="DayNum", how="left")

    # 5. 绘制图形 (同图画出上周与本周两条折线)
    fig2 = go.Figure()

    # 绘制：上周流量 (虚线)
    fig2.add_trace(go.Scatter(
        x=lw_final["DayName"],
        y=lw_final[metric_col],
        mode="lines+markers",
        name=f"上周 ({last_week_start.strftime('%m/%d')} - {last_week_end.strftime('%m/%d')})",
        line=dict(color=color_last_week, width=2, dash="dash"),
        marker=dict(size=7),
        hovertemplate="星期: %{x}<br>上周人次: %{y:,.0f}<extra></extra>"
    ))

    # 绘制：本周流量 (实线加粗)
    fig2.add_trace(go.Scatter(
        x=tw_final["DayName"],
        y=tw_final[metric_col],
        mode="lines+markers",
        name=f"本周 ({this_week_start.strftime('%m/%d')} - {this_week_end.strftime('%m/%d')})",
        line=dict(color=color_this_week, width=4),
        marker=dict(size=8),
        hovertemplate="星期: %{x}<br>本周人次: %{y:,.0f}<extra></extra>"
    ))

    fig2.update_layout(
        title=f"<b>[{selected_port_t2}] {target_title} - 本周 vs 上周对比</b>",
        xaxis_title="星期 (Day of Week)",
        yaxis_title="人次 (Person Times)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=20, r=20, t=50, b=20)
    )

    st.plotly_chart(fig2, width="stretch")


# =====================================================
# TAB 3: 月度日历看板 (Graph 3 预留接口)
# =====================================================

with tab3:
    st.subheader("3. 月度日历天气 & 活动看板")
    st.info("💡 架构预留：在此板块将引入网格日历 (Grid Calendar)，集成香港天文台 (HKO API) 历史天气 icon/气温，以及本地活动写回功能。")