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

try:
    import holidays as py_holidays
except ImportError:
    py_holidays = None

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

from download_data import fetch_latest_immd_data
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
    html { scroll-behavior: smooth; }
    .main { background-color: #f8f9fa; }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
    }
    .insight-box {
        background-color: #ffffff;
        border-left: 4px solid #1E5631;
        padding: 14px 18px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
        margin-top: 10px;
        margin-bottom: 10px;
        font-size: 14px;
        line-height: 1.7;
    }
    .holiday-badge {
        display: inline-block;
        background-color: #fff3cd;
        color: #856404;
        border: 1px solid #ffeeba;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        margin-right: 6px;
    }
    .shift-card {
        background-color: #ffffff;
        border: 1px solid #e9ecef;
        border-radius: 10px;
        padding: 12px 14px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.04);
    }
    .shift-title { font-size: 12px; color: #6c757d; margin-bottom: 4px; }
    .shift-port { font-size: 15px; font-weight: 700; color: #212529; margin-bottom: 4px; line-height: 1.3; }
    .shift-val-up { font-size: 13px; font-weight: 600; color: #1E5631; }
    .shift-val-down { font-size: 13px; font-weight: 600; color: #c9302c; }
    .nav-link {
        display: block;
        padding: 6px 10px;
        margin-bottom: 4px;
        border-radius: 6px;
        color: #212529 !important;
        text-decoration: none !important;
        font-size: 13.5px;
        background-color: #f8f9fa;
        border: 1px solid #e9ecef;
    }
    .nav-link:hover {
        background-color: #e8f5e9;
        border-color: #1E5631;
        color: #1E5631 !important;
    }
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
    .report-table .total-row { 
        font-weight: bold; 
        background-color: #e8f5e9 !important;
        border-top: 2px solid #1E5631;
        border-bottom: 2px solid #1E5631;
    }
    .wow-up { color: #0056b3; font-weight: bold; }
    .wow-down { color: #d9534f; font-weight: bold; }
    .hl-max-arr { background-color: #e8f5e9; color: #14452F; font-weight: 700; padding: 2px 6px; border-radius: 4px; }
    .hl-max-dep { background-color: #e3f2fd; color: #1A3E5C; font-weight: 700; padding: 2px 6px; border-radius: 4px; }
    .pill-top-up { background-color: #e7f1ff; color: #0056b3; font-weight: 700; padding: 2px 8px; border-radius: 10px; }
    .pill-top-down { background-color: #fdecea; color: #c9302c; font-weight: 700; padding: 2px 8px; border-radius: 10px; }
    </style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------
# 2. 混合兜底节假日识别 (2023–2026 精确字典 + 2027+ holidays 库自动识别)
# ---------------------------------------------------------
HOLIDAY_RANGES = [
    # 2023
    ("2023-01-01", "2023-01-02", "元旦(内地&港)"),
    ("2023-01-21", "2023-01-27", "春节(内地 01/21–01/27)"),
    ("2023-01-22", "2023-01-25", "农历新年(港 01/22–01/25)"),
    ("2023-04-05", "2023-04-05", "清明(内地&港 04/05)"),
    ("2023-04-07", "2023-04-10", "复活节(港 04/07–04/10)"),
    ("2023-04-29", "2023-05-03", "五一(内地 04/29–05/03)"),
    ("2023-05-01", "2023-05-01", "劳动节(港 05/01)"),
    ("2023-05-26", "2023-05-26", "佛诞(港 05/26)"),
    ("2023-06-22", "2023-06-24", "端午(内地 06/22–06/24)"),
    ("2023-06-22", "2023-06-22", "端午(港 06/22)"),
    ("2023-07-01", "2023-07-01", "七一(港 07/01)"),
    ("2023-09-29", "2023-10-06", "中秋国庆(内地 09/29–10/06)"),
    ("2023-09-30", "2023-10-02", "中秋国庆(港 09/30–10/02)"),
    ("2023-10-23", "2023-10-23", "重阳(港 10/23)"),
    ("2023-12-25", "2023-12-26", "圣诞(港 12/25–12/26)"),
    # 2024
    ("2024-01-01", "2024-01-01", "元旦(内地&港 01/01)"),
    ("2024-02-10", "2024-02-17", "春节(内地 02/10–02/17)"),
    ("2024-02-10", "2024-02-13", "农历新年(港 02/10–02/13)"),
    ("2024-03-29", "2024-04-01", "复活节(港 03/29–04/01)"),
    ("2024-04-04", "2024-04-06", "清明(内地 04/04–04/06)"),
    ("2024-04-04", "2024-04-04", "清明(港 04/04)"),
    ("2024-05-01", "2024-05-05", "五一(内地 05/01–05/05)"),
    ("2024-05-01", "2024-05-01", "劳动节(港 05/01)"),
    ("2024-05-15", "2024-05-15", "佛诞(港 05/15)"),
    ("2024-06-08", "2024-06-10", "端午(内地 06/08–06/10)"),
    ("2024-06-10", "2024-06-10", "端午(港 06/10)"),
    ("2024-07-01", "2024-07-01", "七一(港 07/01)"),
    ("2024-09-15", "2024-09-17", "中秋(内地 09/15–09/17)"),
    ("2024-09-18", "2024-09-18", "中秋翌日(港 09/18)"),
    ("2024-10-01", "2024-10-07", "国庆(内地 10/01–10/07)"),
    ("2024-10-01", "2024-10-01", "国庆日(港 10/01)"),
    ("2024-10-11", "2024-10-11", "重阳(港 10/11)"),
    ("2024-12-25", "2024-12-26", "圣诞(港 12/25–12/26)"),
    # 2025
    ("2025-01-01", "2025-01-01", "元旦(内地&港 01/01)"),
    ("2025-01-28", "2025-02-04", "春节(内地 01/28–02/04)"),
    ("2025-01-29", "2025-01-31", "农历新年(港 01/29–01/31)"),
    ("2025-04-04", "2025-04-06", "清明(内地 04/04–04/06)"),
    ("2025-04-04", "2025-04-04", "清明(港 04/04)"),
    ("2025-04-18", "2025-04-21", "复活节(港 04/18–04/21)"),
    ("2025-05-01", "2025-05-05", "五一(内地 05/01–05/05)"),
    ("2025-05-01", "2025-05-01", "劳动节(港 05/01)"),
    ("2025-05-05", "2025-05-05", "佛诞(港 05/05)"),
    ("2025-05-31", "2025-06-02", "端午(内地 05/31–06/02)"),
    ("2025-05-31", "2025-05-31", "端午(港 05/31)"),
    ("2025-07-01", "2025-07-01", "七一(港 07/01)"),
    ("2025-10-01", "2025-10-08", "国庆中秋(内地 10/01–10/08)"),
    ("2025-10-01", "2025-10-01", "国庆日(港 10/01)"),
    ("2025-10-07", "2025-10-07", "中秋翌日(港 10/07)"),
    ("2025-10-29", "2025-10-29", "重阳(港 10/29)"),
    ("2025-12-25", "2025-12-26", "圣诞(港 12/25–12/26)"),
    # 2026
    ("2026-01-01", "2026-01-03", "元旦(内地 01/01–01/03)"),
    ("2026-01-01", "2026-01-01", "元旦(港 01/01)"),
    ("2026-02-15", "2026-02-23", "春节(内地 02/15–02/23)"),
    ("2026-02-17", "2026-02-19", "农历新年(港 02/17–02/19)"),
    ("2026-04-04", "2026-04-06", "清明(内地 04/04–04/06)"),
    ("2026-04-03", "2026-04-07", "复活节&清明(港 04/03–04/07)"),
    ("2026-05-01", "2026-05-05", "五一(内地 05/01–05/05)"),
    ("2026-05-01", "2026-05-01", "劳动节(港 05/01)"),
    ("2026-05-24", "2026-05-25", "佛诞(港 05/24–05/25)"),
    ("2026-06-19", "2026-06-21", "端午(内地 06/19–06/21)"),
    ("2026-06-19", "2026-06-19", "端午(港 06/19)"),
    ("2026-07-01", "2026-07-01", "七一(港 07/01)"),
    ("2026-09-25", "2026-09-27", "中秋(内地 09/25–09/27)"),
    ("2026-09-26", "2026-09-26", "中秋翌日(港 09/26)"),
    ("2026-10-01", "2026-10-07", "国庆(内地 10/01–10/07)"),
    ("2026-10-01", "2026-10-01", "国庆日(港 10/01)"),
    ("2026-10-18", "2026-10-19", "重阳(港 10/18–10/19)"),
    ("2026-12-25", "2026-12-26", "圣诞(港 12/25–12/26)"),
]

EXACT_DICT_YEARS = {2023, 2024, 2025, 2026}

def _get_auto_holidays_for_date(dt_val):
    """当某年不在精确字典内时（如 2027+），用 holidays 库自动兜底识别"""
    if py_holidays is None:
        return []
    d_date = dt_val.date()
    yr = d_date.year
    tags = []
    cn_hols = py_holidays.country_holidays("CN", years=yr, language="zh_CN")
    hk_hols = py_holidays.country_holidays("HK", years=yr, language="zh_CN")
    if d_date in cn_hols:
        tags.append(f"{cn_hols.get(d_date)}(内地 {d_date.strftime('%m/%d')})")
    if d_date in hk_hols:
        tags.append(f"{hk_hols.get(d_date)}(港 {d_date.strftime('%m/%d')})")
    return tags

def get_holidays_in_range(start_dt, end_dt):
    found = []
    # 1. 先查精确字典
    for s, e, name in HOLIDAY_RANGES:
        hs, he = pd.Timestamp(s), pd.Timestamp(e)
        if hs <= end_dt and he >= start_dt:
            if name not in found:
                found.append(name)
    # 2. 若区间跨入 2027+ 等未收录年份，自动调用 holidays 库兜底
    cur = start_dt
    while cur <= end_dt:
        if cur.year not in EXACT_DICT_YEARS:
            for t in _get_auto_holidays_for_date(cur):
                if t not in found:
                    found.append(t)
        cur += pd.Timedelta(days=1)
    return found

def get_day_holiday_map(start_dt, end_dt):
    day_map_h = {}
    cur = start_dt
    while cur <= end_dt:
        tags = []
        if cur.year in EXACT_DICT_YEARS:
            for s, e, name in HOLIDAY_RANGES:
                if pd.Timestamp(s) <= cur <= pd.Timestamp(e):
                    short_name = name.split("(")[0]
                    region = "内地" if "内地" in name else ("港" if "港" in name else "")
                    label = f"{short_name}·{region}" if region and "内地&港" not in name else short_name
                    if label not in tags:
                        tags.append(label)
        else:
            for t in _get_auto_holidays_for_date(cur):
                short_name = t.split("(")[0]
                if short_name not in tags:
                    tags.append(short_name)
        if tags:
            day_map_h[cur.dayofweek] = "/".join(tags)
        cur += pd.Timedelta(days=1)
    return day_map_h


# ---------------------------------------------------------
# 3. 侧边栏：导航目录 + 周期选择 + 折叠数据更新
# ---------------------------------------------------------
st.sidebar.title("🇭🇰 Navigation & Controls")

st.sidebar.markdown("""
<div style="margin-bottom: 12px;">
    <a class="nav-link" href="#sec-kpi">📊 1. KPI & Executive Insights</a>
    <a class="nav-link" href="#sec-table">📋 2. Weekly Verification Table</a>
    <a class="nav-link" href="#sec-daily">🗓️ 3. Daily Top-3 Stacked Bars</a>
    <a class="nav-link" href="#sec-macro">📈 4. Historical Overall Trends</a>
    <a class="nav-link" href="#sec-diversion">🔀 5. Control Point Diversion</a>
    <a class="nav-link" href="#sec-huanggang">🏗️ 6. New Huanggang Impact</a>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown("---")

@st.cache_data(ttl=3600)
def get_raw_data():
    return load_data()

try:
    df_raw = get_raw_data()
except Exception as e:
    st.error(f"Data loading failed: {e}")
    st.stop()

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
        status = f"Partial Week ({row['Days_Count']}d: ~{row['Actual_Max'].strftime('%m/%d')})"
    week_options.append(f"{s_str} ~ {e_str} [{status}]")

st.sidebar.subheader("📅 Analysis Period")
selected_base_week_str = st.sidebar.selectbox("Base Week (Current):", week_options, index=0)

base_idx = week_options.index(selected_base_week_str)
base_row = week_stats.iloc[base_idx]
base_start = base_row['Week_Start']
base_end = base_row['Actual_Max']

default_comp_idx = min(base_idx + 1, len(week_options) - 1)
selected_comp_week_str = st.sidebar.selectbox("Comparison Week:", week_options, index=default_comp_idx)
comp_idx = week_options.index(selected_comp_week_str)
comp_row = week_stats.iloc[comp_idx]
comp_start = comp_row['Week_Start']

base_days_count = base_row['Days_Count']
comp_cutoff_date = comp_start + pd.Timedelta(days=base_days_count - 1)

base_df = df_raw[(df_raw["Date"] >= base_start) & (df_raw["Date"] <= base_end)].copy()
comp_df = df_raw[(df_raw["Date"] >= comp_start) & (df_raw["Date"] <= comp_cutoff_date)].copy()

base_holidays = get_holidays_in_range(base_start, base_end)
comp_holidays = get_holidays_in_range(comp_start, comp_cutoff_date)

st.sidebar.markdown("---")
with st.sidebar.expander("⚙️ Data Controls", expanded=False):
    if st.button("⏬ Update to the latest data", use_container_width=True):
        with st.spinner("Downloading from data.gov.hk..."):
            try:
                fetch_latest_immd_data()
                st.success("✅ Updated!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"❌ Failed: {e}")


# ---------------------------------------------------------
# 4. 核心 KPI 汇总卡片 & Executive Insights
# ---------------------------------------------------------
st.markdown('<div id="sec-kpi"></div>', unsafe_allow_html=True)
st.title("🇭🇰 Hong Kong Tourism Dashboard")

if base_days_count < 7:
    st.info(f"💡 **WTD Mode**: Current base week includes first **{base_days_count}** days ({base_start.strftime('%m/%d')} ~ {base_end.strftime('%m/%d')}); comparison week trimmed to ({comp_start.strftime('%m/%d')} ~ {comp_cutoff_date.strftime('%m/%d')}) for fair comparison.")
else:
    st.caption(f"Base Week: {base_start.strftime('%Y-%m-%d')} ~ {base_end.strftime('%Y-%m-%d')} | Comparison Week: {comp_start.strftime('%Y-%m-%d')} ~ {comp_cutoff_date.strftime('%Y-%m-%d')}")

current_p = merge_other(apply_mapping(calculate_port_totals(base_df)))
previous_p = merge_other(apply_mapping(calculate_port_totals(comp_df)))

report_df = merge_current_previous(current_p, previous_p)
report_df = calculate_metrics(report_df)
report_df = sort_report(report_df)
report_df = add_total(report_df)

total_row = report_df[report_df["Group"].isin(["Grand Total", "Total"])].iloc[0]
mainland_base = total_row["Mainland Arrivals"]
mainland_wow = total_row["Arrival WoW %"] * 100 if pd.notnull(total_row["Arrival WoW %"]) else 0
local_base = total_row["Local Departures"]
local_wow = total_row["Departure WoW %"] * 100 if pd.notnull(total_row["Departure WoW %"]) else 0

mainland_comp = comp_df[comp_df["Arrival / Departure"] == "Arrival"]["Mainland Visitors"].sum()
local_comp = comp_df[comp_df["Arrival / Departure"] == "Departure"]["Hong Kong Residents"].sum()

col1, col2, col3, col4 = st.columns(4)
col1.metric(f"Mainland Arrival ({base_days_count}d)", f"{mainland_base:,.0f}", f"{mainland_wow:+.1f}% WoW")
col2.metric(f"Local Departure ({base_days_count}d)", f"{local_base:,.0f}", f"{local_wow:+.1f}% WoW")
col3.metric("Mainland Arrival (Comp)", f"{mainland_comp:,.0f}")
col4.metric("Local Departure (Comp)", f"{local_comp:,.0f}")

df_core = report_df[~report_df["Group"].isin(["Grand Total", "Total", "Other"])].copy()
if not df_core.empty:
    def calc_abs_diff(val, wow):
        if pd.notnull(val) and pd.notnull(wow) and (1 + wow) > 0:
            return val - (val / (1 + wow))
        return 0.0

    df_core["Arr_Diff"] = df_core.apply(lambda r: calc_abs_diff(r["Mainland Arrivals"], r["Arrival WoW %"]), axis=1)
    df_core["Dep_Diff"] = df_core.apply(lambda r: calc_abs_diff(r["Local Departures"], r["Departure WoW %"]), axis=1)

    top_arr_port = df_core.loc[df_core["Mainland Arrivals"].idxmax()]
    top_arr_driver = df_core.loc[df_core["Arr_Diff"].abs().idxmax()]
    top_dep_port = df_core.loc[df_core["Local Departures"].idxmax()]
    top_dep_driver = df_core.loc[df_core["Dep_Diff"].abs().idxmax()]

    arr_driver_dir = "增长" if top_arr_driver["Arr_Diff"] >= 0 else "回落"
    dep_driver_dir = "增长" if top_dep_driver["Dep_Diff"] >= 0 else "回落"

    holiday_line = ""
    if base_holidays or comp_holidays:
        b_h = "、".join(base_holidays) if base_holidays else "无"
        c_h = "、".join(comp_holidays) if comp_holidays else "无"
        holiday_line = f'• <span class="holiday-badge">🗓️ 假期影响提示</span> Base Week 含：<b>{b_h}</b> ｜ Comparison Week 含：<b>{c_h}</b><br>'

    st.markdown(
    f'<div class="insight-box">'
    f'<div style="font-size: 16px; font-weight: 700; color: #1E5631; margin-bottom: 6px;">📌 Executive Insights（本周核心洞察）</div>'
    f'{holiday_line}'
    f'<div style="margin: 3px 0;">• <b>内地访港 (Mainland Arrival)</b>：总体环比 <b>{mainland_wow:+.1f}%</b>；最大入境口岸为 <b>{top_arr_port["Display Name"]}</b>（占 <b>{top_arr_port["Arrival Share"]:.1%}</b>），本期绝对客流{arr_driver_dir}主力为 <b>{top_arr_driver["Display Name"]}</b>（{top_arr_driver["Arr_Diff"]:+,.0f} 人次 / {top_arr_driver["Arrival WoW %"]:+.1%}）。</div>'
    f'<div style="margin: 3px 0;">• <b>港人离境 (Local Departure)</b>：总体环比 <b>{local_wow:+.1f}%</b>；最大出境口岸为 <b>{top_dep_port["Display Name"]}</b>（占 <b>{top_dep_port["Departure Share"]:.1%}</b>），本期绝对客流{dep_driver_dir}主力为 <b>{top_dep_driver["Display Name"]}</b>（{top_dep_driver["Dep_Diff"]:+,.0f} 人次 / {top_dep_driver["Departure WoW %"]:+.1%}）。</div>'
    f'</div>',
    unsafe_allow_html=True
    )


st.markdown("---")


# ---------------------------------------------------------
# 5. 数据表格 (清爽版高亮 + 标题栏节假日标注)
# ---------------------------------------------------------
st.markdown('<div id="sec-table"></div>', unsafe_allow_html=True)
st.subheader("📋 Weekly Report Data Verification Table")

def render_custom_table(df, b_start, b_end, c_start, c_end, b_hols, c_hols):
    base_date_str = f"{b_start.strftime('%d/%m/%Y')} - {b_end.strftime('%d/%m/%Y')}"
    comp_date_str = f"{c_start.strftime('%d/%m/%Y')} - {c_end.strftime('%d/%m/%Y')}"
    b_tag = f' <span class="holiday-badge">含: {", ".join(b_hols)}</span>' if b_hols else ""
    c_tag = f' <span class="holiday-badge">含: {", ".join(c_hols)}</span>' if c_hols else ""

    non_total = df[~df["Group"].isin(["Grand Total", "Total"])]
    max_arr_idx = non_total["Mainland Arrivals"].idxmax() if not non_total.empty else None
    max_dep_idx = non_total["Local Departures"].idxmax() if not non_total.empty else None

    wow_pool = df[~df["Group"].isin(["Grand Total", "Total", "Other"])]
    arr_pos = wow_pool[wow_pool["Arrival WoW %"] > 0]["Arrival WoW %"]
    arr_neg = wow_pool[wow_pool["Arrival WoW %"] < 0]["Arrival WoW %"]
    max_arr_wow_idx = arr_pos.idxmax() if not arr_pos.empty else None
    min_arr_wow_idx = arr_neg.idxmin() if not arr_neg.empty else None

    dep_pos = wow_pool[wow_pool["Departure WoW %"] > 0]["Departure WoW %"]
    dep_neg = wow_pool[wow_pool["Departure WoW %"] < 0]["Departure WoW %"]
    max_dep_wow_idx = dep_pos.idxmax() if not dep_pos.empty else None
    min_dep_wow_idx = dep_neg.idxmin() if not dep_neg.empty else None

    html_code = f"""
    <div style="margin-bottom: 8px; font-weight: bold; color: #1E5631; line-height: 1.8;">
        <div>Base Period: <span style="color:#000;">{base_date_str}</span>{b_tag}</div>
        <div>Comparison Period (Audit): <span style="color:#000;">{comp_date_str}</span>{c_tag}</div>
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
        html_code += f'<td>{row["Group"]}</td><td>{row["Display Name"]}</td>'
        
        arr_val = f"{row['Mainland Arrivals']:,.0f}" if pd.notnull(row['Mainland Arrivals']) else "-"
        if idx == max_arr_idx:
            arr_val = f'<span class="hl-max-arr">{arr_val}</span>'
        html_code += f'<td>{arr_val}</td>'
        
        arr_share = f"{row['Arrival Share']:.1%}" if pd.notnull(row['Arrival Share']) and not np.isnan(row['Arrival Share']) else "-"
        html_code += f'<td>{arr_share}</td>'
        
        arr_wow_val = row['Arrival WoW %']
        if pd.notnull(arr_wow_val) and not np.isnan(arr_wow_val):
            if idx == max_arr_wow_idx:
                arr_wow_html = f'<span class="pill-top-up">↑ {abs(arr_wow_val):.1%}</span>'
            elif idx == min_arr_wow_idx:
                arr_wow_html = f'<span class="pill-top-down">↓ {abs(arr_wow_val):.1%}</span>'
            elif arr_wow_val > 0:
                arr_wow_html = f'<span class="wow-up">↑ {abs(arr_wow_val):.1%}</span>'
            elif arr_wow_val < 0:
                arr_wow_html = f'<span class="wow-down">↓ {abs(arr_wow_val):.1%}</span>'
            else:
                arr_wow_html = f'{arr_wow_val:.1%}'
        else:
            arr_wow_html = "-"
        html_code += f'<td>{arr_wow_html}</td>'
        
        dep_val = f"{row['Local Departures']:,.0f}" if pd.notnull(row['Local Departures']) else "-"
        if idx == max_dep_idx:
            dep_val = f'<span class="hl-max-dep">{dep_val}</span>'
        html_code += f'<td>{dep_val}</td>'
        
        dep_share = f"{row['Departure Share']:.1%}" if pd.notnull(row['Departure Share']) and not np.isnan(row['Departure Share']) else "-"
        html_code += f'<td>{dep_share}</td>'
        
        dep_wow_val = row['Departure WoW %']
        if pd.notnull(dep_wow_val) and not np.isnan(dep_wow_val):
            if idx == max_dep_wow_idx:
                dep_wow_html = f'<span class="pill-top-up">↑ {abs(dep_wow_val):.1%}</span>'
            elif idx == min_dep_wow_idx:
                dep_wow_html = f'<span class="pill-top-down">↓ {abs(dep_wow_val):.1%}</span>'
            elif dep_wow_val > 0:
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

st.html(render_custom_table(report_df, base_start, base_end, comp_start, comp_cutoff_date, base_holidays, comp_holidays))
st.markdown("---")


# ---------------------------------------------------------
# 6. 每日对比：并排分组 + Top 3 口岸 & 浅灰 Other 堆叠柱状图
# ---------------------------------------------------------
st.markdown('<div id="sec-daily"></div>', unsafe_allow_html=True)
st.subheader("🗓️ Daily Comparison within the Weeks (Top 3 Borders + Other)")

day_map = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri', 5: 'Sat', 6: 'Sun'}
base_day_hols = get_day_holiday_map(base_start, base_end)

def get_daily_port_df(df_sub):
    frames = []
    for d, df_day in df_sub.groupby("Date"):
        p = merge_other(apply_mapping(calculate_port_totals(df_day)))
        p_fmt = merge_current_previous(p, p)
        p_grp = p_fmt.groupby("Display Name", as_index=False)[["Mainland Arrivals", "Local Departures"]].sum()
        p_grp["Date"] = d
        frames.append(p_grp)
    if not frames:
        return pd.DataFrame()
    res = pd.concat(frames, ignore_index=True)
    res["DayOfWeek"] = res["Date"].dt.dayofweek
    return res

base_daily_ports = get_daily_port_df(base_df)
comp_daily_ports = get_daily_port_df(comp_df)

def build_grouped_stacked_chart(df_b, df_c, metric_col, title_str, base_palette, comp_palette):
    if df_b.empty:
        return go.Figure()

    top3_ports = (
        df_b.groupby("Display Name")[metric_col]
        .sum()
        .sort_values(ascending=False)
        .head(3)
        .index.tolist()
    )
    categories = top3_ports + ["Other"]

    def prep_grouped(df_in):
        if df_in.empty:
            return pd.DataFrame(columns=["DayOfWeek", "Port_Cat", metric_col])
        temp = df_in.copy()
        temp["Port_Cat"] = temp["Display Name"].where(temp["Display Name"].isin(top3_ports), "Other")
        return temp.groupby(["DayOfWeek", "Port_Cat"], as_index=False)[metric_col].sum()

    b_agg = prep_grouped(df_b)
    c_agg = prep_grouped(df_c)

    b_date_map = df_b.groupby("DayOfWeek")["Date"].first().to_dict()
    days_present = sorted(b_agg["DayOfWeek"].unique())
    day_labels = []
    for d in days_present:
        d_str = b_date_map[d].strftime("%m/%d")
        if d in base_day_hols:
            day_labels.append(f"{day_map[d]}<br>{d_str} ({base_day_hols[d]})")
        else:
            day_labels.append(f"{day_map[d]}<br>{d_str}")

    fig = go.Figure()

    for idx, cat in enumerate(categories):
        y_vals = [b_agg[(b_agg["DayOfWeek"] == d) & (b_agg["Port_Cat"] == cat)][metric_col].sum() for d in days_present]
        fig.add_trace(go.Bar(
            name=f"{cat} (Base)",
            x=day_labels,
            y=y_vals,
            offsetgroup="Base",
            legendgroup="Base",
            marker_color=base_palette[idx % len(base_palette)],
            text=[f"{v/1000:.1f}k" if v >= 3000 else "" for v in y_vals],
            textposition="inside",
            hovertemplate="%{y:,.0f}<extra>%{fullData.name}</extra>"
        ))

    for idx, cat in enumerate(categories):
        y_vals = [c_agg[(c_agg["DayOfWeek"] == d) & (c_agg["Port_Cat"] == cat)][metric_col].sum() for d in days_present]
        fig.add_trace(go.Bar(
            name=f"{cat} (Comp)",
            x=day_labels,
            y=y_vals,
            offsetgroup="Comp",
            legendgroup="Comp",
            marker_color=comp_palette[idx % len(comp_palette)],
            text=[f"{v/1000:.1f}k" if v >= 3000 else "" for v in y_vals],
            textposition="inside",
            hovertemplate="%{y:,.0f}<extra>%{fullData.name}</extra>"
        ))

    fig.update_layout(
        title=dict(text=title_str, y=0.96, x=0),
        barmode="stack",
        height=450,
        hovermode="x unified",
        yaxis_title="Passengers (人次)",
        xaxis_title="",
        margin=dict(t=115, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)
    )
    return fig

green_base = ["#14452F", "#1E6B47", "#349B68", "#D6DCE0"]
green_comp = ["#6C8E7F", "#88A99A", "#A8C3B6", "#EAECEF"]

blue_base = ["#1A3E5C", "#2B5B84", "#4A82B0", "#D6DCE0"]
blue_comp = ["#6B8296", "#879CB0", "#A6B8C9", "#EAECEF"]

st.plotly_chart(
    build_grouped_stacked_chart(
        base_daily_ports, comp_daily_ports, "Mainland Arrivals",
        "Mainland Arrival Daily Comparison (Left: Base | Right: Comp)",
        green_base, green_comp
    ),
    use_container_width=True
)

st.plotly_chart(
    build_grouped_stacked_chart(
        base_daily_ports, comp_daily_ports, "Local Departures",
        "Local Departure Daily Comparison (Left: Base | Right: Comp)",
        blue_base, blue_comp
    ),
    use_container_width=True
)

st.markdown("---")


# ---------------------------------------------------------
# 7. 历史趋势折线图 (关闭 Range Slider + 7日均线 + 错层标注)
# ---------------------------------------------------------
st.markdown('<div id="sec-macro"></div>', unsafe_allow_html=True)
st.subheader("📈 Historical Daily Traffic Trends & Key Milestones")

ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([3, 1.5, 1.5])
with ctrl_col1:
    timeframe = st.radio(
        "Timeframe:",
        ["1W", "1M", "6M", "1Y", "3Y", "All"],
        index=3,
        horizontal=True,
        key="macro_tf"
    )
with ctrl_col2:
    use_ma7 = st.checkbox("7-Day Moving Average (7-Day MA)", value=True, key="macro_ma7")
with ctrl_col3:
    show_milestones = st.checkbox("Show Holiday & Port Markers", value=True, key="macro_mk")

MILESTONES = [
    ("2023-01-08", "Border Reopen", "#6f42c1"),
    ("2023-02-06", "Huanggang Reopen", "#6f42c1"),
    ("2023-04-29", "May Day '23", "#d9534f"),
    ("2023-09-29", "Golden Week '23", "#d9534f"),
    ("2024-02-10", "CNY '24", "#d9534f"),
    ("2024-03-29", "Easter '24", "#e67e22"),
    ("2024-05-01", "May Day '24", "#d9534f"),
    ("2024-07-01", "HK SAR Day '24", "#e67e22"),
    ("2024-10-01", "Golden Week '24", "#d9534f"),
    ("2024-12-25", "Christmas '24", "#e67e22"),
    ("2025-01-29", "CNY '25", "#d9534f"),
    ("2025-04-18", "Easter '25", "#e67e22"),
    ("2025-05-01", "May Day '25", "#d9534f"),
    ("2025-07-01", "HK SAR Day '25", "#e67e22"),
    ("2025-10-01", "Golden Week '25", "#d9534f"),
    ("2025-12-25", "Christmas '25", "#e67e22"),
    ("2026-02-17", "CNY '26", "#d9534f"),
    ("2026-04-03", "Easter '26", "#e67e22"),
    ("2026-05-01", "May Day '26", "#d9534f"),
    ("2026-07-01", "HK SAR Day '26", "#e67e22"),
    ("2026-10-01", "Golden Week '26", "#d9534f"),
    ("2026-10-12", "New Huanggang Port", "#6f42c1"),
]

def get_start_date(max_dt, tf):
    if tf == "1W":
        return max_dt - pd.Timedelta(days=7)
    elif tf == "1M":
        return max_dt - pd.DateOffset(months=1)
    elif tf == "6M":
        return max_dt - pd.DateOffset(months=6)
    elif tf == "1Y":
        return max_dt - pd.DateOffset(years=1)
    elif tf == "3Y":
        return max_dt - pd.DateOffset(years=3)
    return None

def add_milestone_markers(fig, min_d, max_d):
    visible = [(pd.Timestamp(d), d, lbl, clr) for d, lbl, clr in MILESTONES if min_d <= pd.Timestamp(d) <= max_d]
    last_dt = None
    stagger = False
    for m_dt, m_date_str, m_label, m_color in visible:
        if last_dt is not None and (m_dt - last_dt).days < 40:
            stagger = not stagger
        else:
            stagger = False
        y_pos = 1.09 if stagger else 1.01
        last_dt = m_dt

        fig.add_vline(x=m_date_str, line_width=1, line_dash="dot", line_color=m_color, opacity=0.65)
        fig.add_annotation(
            x=m_date_str,
            y=y_pos,
            yref="paper",
            text=m_label,
            showarrow=False,
            textangle=-30,
            font=dict(size=10, color=m_color),
            xanchor="left",
            yanchor="bottom"
        )

df_all_arr = df_raw[df_raw["Arrival / Departure"] == "Arrival"].groupby("Date")["Mainland Visitors"].sum().reset_index()
df_all_dep = df_raw[df_raw["Arrival / Departure"] == "Departure"].groupby("Date")["Hong Kong Residents"].sum().reset_index()
df_macro = pd.merge(df_all_arr, df_all_dep, on="Date").sort_values("Date")

if use_ma7:
    df_macro["Mainland Visitors"] = df_macro["Mainland Visitors"].rolling(7, min_periods=1).mean()
    df_macro["Hong Kong Residents"] = df_macro["Hong Kong Residents"].rolling(7, min_periods=1).mean()

max_dt = df_macro["Date"].max()
start_dt = get_start_date(max_dt, timeframe)
df_macro_view = df_macro[df_macro["Date"] >= start_dt] if start_dt is not None else df_macro

ma_tag = "7-Day MA" if use_ma7 else "Daily"
fig_macro = px.line(
    df_macro_view,
    x="Date",
    y=["Mainland Visitors", "Hong Kong Residents"],
    title=f"Overall Traffic Trends ({timeframe} | {ma_tag})",
    color_discrete_map={"Mainland Visitors": "#1E5631", "Hong Kong Residents": "#2B5B84"},
    labels={"value": "Passengers", "variable": "Traffic Type", "Date": "Date"}
)
fig_macro.update_traces(hovertemplate="%{y:,.0f}<extra>%{fullData.name}</extra>")

if show_milestones and not df_macro_view.empty:
    add_milestone_markers(fig_macro, df_macro_view["Date"].min(), df_macro_view["Date"].max())

fig_macro.update_xaxes(rangeslider_visible=False)
fig_macro.update_layout(
    title=dict(y=0.98, x=0),
    height=460,
    hovermode="x unified",
    margin=dict(t=135, b=70),
    legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5, title_text="")
)
st.plotly_chart(fig_macro, use_container_width=True)

st.markdown("---")


# ---------------------------------------------------------
# 8. 各关口分流趋势折线图 (合并旧皇岗+新皇岗 + 默认 Top 5 + 底部图例)
# ---------------------------------------------------------
st.markdown('<div id="sec-diversion"></div>', unsafe_allow_html=True)
st.subheader("🔀 Control Point Traffic Diversion Trends")

OLD_HUANGGANG_NAMES = {"Lok Ma Chau(舊皇崗)", "Lok Ma Chau (舊皇崗)", "Lok Ma Chau(旧皇岗)", "Lok Ma Chau"}

@st.cache_data(ttl=3600)
def get_all_dates_port_history(df_all):
    frames = []
    for d, df_day in df_all.groupby("Date"):
        p = apply_mapping(calculate_port_totals(df_day))
        p_fmt = merge_current_previous(p, p)
        p_fmt["Display Name"] = p_fmt["Display Name"].replace(list(OLD_HUANGGANG_NAMES), "Huanggang")
        p_grp = p_fmt.groupby("Display Name", as_index=False)[["Mainland Arrivals", "Local Departures"]].sum()
        p_grp["Date"] = d
        frames.append(p_grp)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True).sort_values(["Display Name", "Date"])

with st.spinner("Loading control point trend lines..."):
    df_port_hist = get_all_dates_port_history(df_raw)

if not df_port_hist.empty:
    hist_max_dt = df_port_hist["Date"].max()
    recent_7 = df_port_hist[df_port_hist["Date"] > hist_max_dt - pd.Timedelta(days=7)]
    prev_7 = df_port_hist[
        (df_port_hist["Date"] <= hist_max_dt - pd.Timedelta(days=23)) &
        (df_port_hist["Date"] > hist_max_dt - pd.Timedelta(days=30))
    ]
    if not recent_7.empty and not prev_7.empty:
        def get_share_shift_clean(col_name):
            r_all = recent_7.groupby("Display Name")[col_name].sum()
            p_all = prev_7.groupby("Display Name")[col_name].sum()
            r_sh = (r_all / r_all.sum() * 100) if r_all.sum() > 0 else r_all * 0
            p_sh = (p_all / p_all.sum() * 100) if p_all.sum() > 0 else p_all * 0
            diff = (r_sh - p_sh).dropna()
            diff = diff[diff.index != "Other"].sort_values(ascending=False)
            return diff

        arr_shift = get_share_shift_clean("Mainland Arrivals")
        dep_shift = get_share_shift_clean("Local Departures")
        if len(arr_shift) >= 2 and len(dep_shift) >= 2:
            st.caption("🔄 **Share Shift (Last 7 Days vs 1 Month Ago, excl. Other)**: Quick view of port share movement")
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                st.markdown(f'<div class="shift-card"><div class="shift-title">Arrival Top Gainer</div><div class="shift-port">{arr_shift.index[0]}</div><div class="shift-val-up">{arr_shift.iloc[0]:+.2f}% share</div></div>', unsafe_allow_html=True)
            with s2:
                st.markdown(f'<div class="shift-card"><div class="shift-title">Arrival Top Drop</div><div class="shift-port">{arr_shift.index[-1]}</div><div class="shift-val-down">{arr_shift.iloc[-1]:+.2f}% share</div></div>', unsafe_allow_html=True)
            with s3:
                st.markdown(f'<div class="shift-card"><div class="shift-title">Departure Top Gainer</div><div class="shift-port">{dep_shift.index[0]}</div><div class="shift-val-up">{dep_shift.iloc[0]:+.2f}% share</div></div>', unsafe_allow_html=True)
            with s4:
                st.markdown(f'<div class="shift-card"><div class="shift-title">Departure Top Drop</div><div class="shift-port">{dep_shift.index[-1]}</div><div class="shift-val-down">{dep_shift.iloc[-1]:+.2f}% share</div></div>', unsafe_allow_html=True)
            st.write("")

    div_ctrl1, div_ctrl2, div_ctrl3, div_ctrl4 = st.columns([2.5, 2, 1.3, 1.3])
    with div_ctrl1:
        div_timeframe = st.radio(
            "Diversion Timeframe:",
            ["1W", "1M", "6M", "1Y", "3Y", "All"],
            index=3,
            horizontal=True,
            key="div_tf"
        )
    with div_ctrl2:
        div_metric_mode = st.radio(
            "Diversion Metric:",
            ["Passenger Volume", "Port Share (%)"],
            horizontal=True,
            key="div_metric"
        )
    with div_ctrl3:
        div_use_ma7 = st.checkbox("7-Day MA", value=True, key="div_ma7")
    with div_ctrl4:
        div_show_mk = st.checkbox("Show Markers", value=True, key="div_mk")

    recent_rank_df = df_port_hist[df_port_hist["Date"] > hist_max_dt - pd.Timedelta(days=30)]
    all_ports_sorted = (
        recent_rank_df.groupby("Display Name")["Mainland Arrivals"]
        .sum()
        .sort_values(ascending=False)
        .index.tolist()
    )
    default_ports = [p for p in all_ports_sorted if p != "Other"][:5]
    if "Huanggang" in all_ports_sorted and "Huanggang" not in default_ports:
        default_ports.append("Huanggang")

    selected_ports = st.multiselect(
        "Control Points Displayed (Default: Top 5 + Huanggang; add/remove below):",
        options=all_ports_sorted,
        default=default_ports
    )

    div_start_dt = get_start_date(hist_max_dt, div_timeframe)
    div_ma_tag = "7-Day MA" if div_use_ma7 else "Daily"

    def render_port_line_chart(df_hist, value_col, chart_title):
        if not selected_ports:
            st.warning("Please select at least one control point.")
            return

        if div_metric_mode == "Port Share (%)":
            daily_totals = df_hist.groupby("Date")[value_col].transform("sum")
            df_tmp = df_hist.copy()
            df_tmp["PlotVal"] = np.where(daily_totals > 0, df_tmp[value_col] / daily_totals * 100, 0)
            df_sub = df_tmp[df_tmp["Display Name"].isin(selected_ports)].copy()
            y_label = "Share (%)"
            hover_fmt = "%{y:.1f}%<extra>%{fullData.name}</extra>"
        else:
            df_sub = df_hist[df_hist["Display Name"].isin(selected_ports)].copy()
            df_sub["PlotVal"] = df_sub[value_col]
            y_label = "Passengers"
            hover_fmt = "%{y:,.0f}<extra>%{fullData.name}</extra>"

        df_sub = df_sub.sort_values(["Display Name", "Date"])
        if div_use_ma7:
            df_sub["PlotVal"] = df_sub.groupby("Display Name")["PlotVal"].transform(
                lambda s: s.rolling(7, min_periods=1).mean()
            )

        if div_start_dt is not None:
            df_sub = df_sub[df_sub["Date"] >= div_start_dt]

        fig_p = px.line(
            df_sub,
            x="Date",
            y="PlotVal",
            color="Display Name",
            title=f"{chart_title} ({div_timeframe} | {div_ma_tag})",
            labels={"PlotVal": y_label, "Date": "Date", "Display Name": "Control Point"}
        )
        fig_p.update_traces(hovertemplate=hover_fmt)

        if div_show_mk and not df_sub.empty:
            add_milestone_markers(fig_p, df_sub["Date"].min(), df_sub["Date"].max())

        fig_p.update_layout(
            title=dict(y=0.98, x=0),
            height=500,
            hovermode="x unified",
            margin=dict(t=135, b=110),
            legend=dict(orientation="h", yanchor="top", y=-0.16, xanchor="center", x=0.5, title_text="")
        )
        st.plotly_chart(fig_p, use_container_width=True)

    render_port_line_chart(df_port_hist, "Mainland Arrivals", "Mainland Arrival by Control Point")
    render_port_line_chart(df_port_hist, "Local Departures", "Local Departure by Control Point")


# ---------------------------------------------------------
# 9. 专项归因分析：新皇岗口岸启用 (2026-10-12) 首月对称对比
# ---------------------------------------------------------
st.markdown("---")
st.markdown('<div id="sec-huanggang"></div>', unsafe_allow_html=True)
st.subheader("🏗️ Impact Analysis: New Huanggang Port (Opened 2026-10-12)")

OPEN_DATE = pd.Timestamp("2026-10-12")
if not df_port_hist.empty and df_port_hist["Date"].max() >= OPEN_DATE:
    hg_col1, hg_col2 = st.columns(2)
    with hg_col1:
        after_opt = st.radio(
            "After-Opening Evaluation Window:",
            ["First 30 Days Post-Opening (2026-10-12 ~ 11-10, Rigorous)", "Latest 30 Days (Current Steady-State)"],
            horizontal=False
        )
    with hg_col2:
        baseline_opt = st.radio(
            "Before-Opening Baseline (Excl. Oct 1–7 Golden Week):",
            ["Pre-Golden Week Normal Days (2026-09-01 ~ 09-24)", "Aug–Sep Normal Days (2026-08-01 ~ 09-24)"],
            horizontal=False
        )

    b_start_hg = pd.Timestamp("2026-09-01") if "09-01" in baseline_opt else pd.Timestamp("2026-08-01")
    b_end_hg = pd.Timestamp("2026-09-24")

    latest_dt = df_port_hist["Date"].max()
    if "First 30 Days" in after_opt:
        a_start_hg = OPEN_DATE
        a_end_hg = min(OPEN_DATE + pd.Timedelta(days=29), latest_dt)
    else:
        a_end_hg = latest_dt
        a_start_hg = max(OPEN_DATE, latest_dt - pd.Timedelta(days=29))

    df_before_hg = df_port_hist[(df_port_hist["Date"] >= b_start_hg) & (df_port_hist["Date"] <= b_end_hg)]
    df_after_hg = df_port_hist[(df_port_hist["Date"] >= a_start_hg) & (df_port_hist["Date"] <= a_end_hg)]

    b_days_hg = df_before_hg["Date"].nunique()
    a_days_hg = df_after_hg["Date"].nunique()
    st.caption(
        f"📅 **Comparison Window**: After (`{a_start_hg.strftime('%Y-%m-%d')} ~ {a_end_hg.strftime('%Y-%m-%d')}`, {a_days_hg}d) "
        f"vs Before (`{b_start_hg.strftime('%Y-%m-%d')} ~ {b_end_hg.strftime('%Y-%m-%d')}`, {b_days_hg}d)"
    )

    def calc_impact_df(col_name):
        b_avg = df_before_hg.groupby("Display Name")[col_name].mean()
        a_avg = df_after_hg.groupby("Display Name")[col_name].mean()
        imp = pd.DataFrame({"Before Daily Avg": b_avg, "After Daily Avg": a_avg}).fillna(0)
        imp = imp[imp.index != "Other"]
        b_tot = imp["Before Daily Avg"].sum()
        a_tot = imp["After Daily Avg"].sum()
        imp["Before Share (%)"] = np.where(b_tot > 0, imp["Before Daily Avg"] / b_tot * 100, 0)
        imp["After Share (%)"] = np.where(a_tot > 0, imp["After Daily Avg"] / a_tot * 100, 0)
        imp["Share Change (pp)"] = imp["After Share (%)"] - imp["Before Share (%)"]
        imp["Daily Diff"] = imp["After Daily Avg"] - imp["Before Daily Avg"]
        return imp.sort_values("Share Change (pp)")

    imp_arr = calc_impact_df("Mainland Arrivals")
    imp_dep = calc_impact_df("Local Departures")

    hg_c1, hg_c2 = st.columns(2)

    def plot_diverging_share(imp_df, title_text):
        colors = ["#c9302c" if v < 0 else "#1E5631" for v in imp_df["Share Change (pp)"]]
        labels_fmt = [f"{v:+.2f} pp" for v in imp_df["Share Change (pp)"]]

        x_min = min(imp_df["Share Change (pp)"].min(), 0)
        x_max = max(imp_df["Share Change (pp)"].max(), 0)
        pad = max(abs(x_min), abs(x_max), 1.0) * 0.45

        fig_d = go.Figure(go.Bar(
            x=imp_df["Share Change (pp)"],
            y=imp_df.index,
            orientation="h",
            marker_color=colors,
            text=labels_fmt,
            customdata=labels_fmt,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="<b>%{y}</b><br>Share Change: %{customdata}<extra></extra>"
        ))
        fig_d.add_vline(x=0, line_width=1, line_color="#6c757d")
        fig_d.update_layout(
            title=title_text,
            height=430,
            xaxis=dict(title="Share Change (Percentage Points)", range=[x_min - pad, x_max + pad]),
            yaxis_title="",
            margin=dict(l=15, r=30, t=55, b=40)
        )
        return fig_d

    with hg_c1:
        st.plotly_chart(plot_diverging_share(imp_arr, "Mainland Arrival: Share Shift"), use_container_width=True)
    with hg_c2:
        st.plotly_chart(plot_diverging_share(imp_dep, "Local Departure: Share Shift"), use_container_width=True)

    with st.expander("📊 View Detailed Before vs After Daily Average Table", expanded=False):
        tab_arr, tab_dep = st.tabs(["Mainland Arrival Impact", "Local Departure Impact"])
        with tab_arr:
            st.dataframe(
                imp_arr.sort_values("Share Change (pp)", ascending=False).style.format({
                    "Before Daily Avg": "{:,.0f}",
                    "After Daily Avg": "{:,.0f}",
                    "Daily Diff": "{:+,.0f}",
                    "Before Share (%)": "{:.1f}%",
                    "After Share (%)": "{:.1f}%",
                    "Share Change (pp)": "{:+.2f} pp"
                }),
                use_container_width=True
            )
        with tab_dep:
            st.dataframe(
                imp_dep.sort_values("Share Change (pp)", ascending=False).style.format({
                    "Before Daily Avg": "{:,.0f}",
                    "After Daily Avg": "{:,.0f}",
                    "Daily Diff": "{:+,.0f}",
                    "Before Share (%)": "{:.1f}%",
                    "After Share (%)": "{:.1f}%",
                    "Share Change (pp)": "{:+.2f} pp"
                }),
                use_container_width=True
            )
else:
    st.info("Data does not yet cover 2026-10-12 onwards.")
