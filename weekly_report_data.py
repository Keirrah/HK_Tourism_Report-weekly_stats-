#%%
import sys
import subprocess

# 定义自动化流程所依赖的所有 Python 包
REQUIRED_PACKAGES = [
    "pandas",
    "openpyxl",
    "numpy",
    "matplotlib",
    "seaborn",
    "requests",
    "plotly"  
]

def auto_setup_environment(packages):
    """
    自动检测当前电脑的 Python 环境，如缺少第三方包则自动静默安装
    """
    installed_packages = []
    missing_packages = []

    for pkg in packages:
        try:
            __import__(pkg)
            installed_packages.append(pkg)
        except ImportError:
            missing_packages.append(pkg)

    if missing_packages:
        print(f"检测到当前电脑缺少以下程序包: {missing_packages}")
        print("正在为您自动安装，请稍候...\n")
        
        for pkg in missing_packages:
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])
                print(f" {pkg} 安装成功！")
            except Exception as e:
                print(f"❌ {pkg} 安装失败，错误信息: {e}")
        print("\n🎉 所有缺失包已补齐，即将继续执行主程序！\n" + "="*50)
    else:
        print(" 环境检测通过：所有依赖包已就绪！\n")

# 执行环境检查
auto_setup_environment(REQUIRED_PACKAGES)


# =====================================================
# 正常 import 依赖库
# =====================================================
import json
import webbrowser
import shutil
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import plotly.express as px

from download_data import fetch_latest_immd_data, clean_and_parse_dates


# =====================================================
# 核心控制配置 (Control Configuration)
# =====================================================
# TARGET_DATE: 设定你需要计算的目标周内的任意一天日期，例如 "2026-07-20"
# 如果设置为 None，则系统自动取数据文件中的【最新完整周】
TARGET_DATE = None  # 示例: "2026-07-20"


# =====================================================
# File Path Configurations
# =====================================================
BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATE_DIR = BASE_DIR / "template"

RAW_FILE = INPUT_DIR / "latest_immd_raw.csv"
MAPPING_FILE = TEMPLATE_DIR / "port_mapping.xlsx"

OUTPUT_DIR.mkdir(exist_ok=True)
INPUT_DIR.mkdir(exist_ok=True)


# =====================================================
# Data Processing Pipeline (Pandas)
# =====================================================
def load_data():
    df = pd.read_csv(RAW_FILE)
    df.columns = df.columns.str.strip()  # 去除列名空格
    
    # 统一调用单一点日期解析逻辑
    df["Date"] = clean_and_parse_dates(df["Date"])
    df = df.dropna(subset=["Date"])
    
    # 填充与数值格式清洗
    numeric_cols = ["Hong Kong Residents", "Mainland Visitors", "Other Visitors", "Total"]
    for col in numeric_cols:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(",", "")
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            
    return df


def get_complete_week(df, target_date_str=None):
    """
    支持根据 TARGET_DATE 灵活切周：
    - 若指定 target_date_str，定位该日期所在完整自然周 (Mon-Sun)
    - 若未指定 (None)，定位最新完整自然周
    """
    if target_date_str:
        anchor_date = pd.to_datetime(target_date_str)
        if anchor_date > df["Date"].max() or anchor_date < df["Date"].min():
            raise ValueError(f"❌ 指定日期 {target_date_str} 超出数据实际范围 ({df['Date'].min().strftime('%Y-%m-%d')} ~ {df['Date'].max().strftime('%Y-%m-%d')})")
    else:
        anchor_date = df["Date"].max()
    
    # 按照周一到周日对齐自然周 (0=Mon, 6=Sun)
    current_week_mon = anchor_date - pd.Timedelta(days=anchor_date.weekday())
    
    # 若最新一天尚未填满到本周日且未指定日期，则取上一个完整自然周
    if target_date_str is None and anchor_date < current_week_mon + pd.Timedelta(days=6):
        latest_end = current_week_mon - pd.Timedelta(days=1)   # 上周日
        latest_start = latest_end - pd.Timedelta(days=6)        # 上周一
    else:
        latest_end = current_week_mon + pd.Timedelta(days=6)    # 本周日
        latest_start = current_week_mon                        # 本周一

    previous_end = latest_start - pd.Timedelta(days=1)
    previous_start = previous_end - pd.Timedelta(days=6)

    print(f"   - 锚定参考日期: {anchor_date.strftime('%Y-%m-%d')}")
    print(f"   - 本周区间 (Mon-Sun): {latest_start.strftime('%Y-%m-%d')} ~ {latest_end.strftime('%Y-%m-%d')}")
    print(f"   - 上周区间 (Mon-Sun): {previous_start.strftime('%Y-%m-%d')} ~ {previous_end.strftime('%Y-%m-%d')}\n")

    return {
        "current_start": latest_start,
        "current_end": latest_end,
        "previous_start": previous_start,
        "previous_end": previous_end,
    }


def filter_week(df, start, end):
    result = df[(df["Date"] >= start) & (df["Date"] <= end)].copy()
    
    found_dates = result["Date"].dt.strftime("%Y-%m-%d").unique()
    if len(found_dates) != 7:
        expected_dates = pd.date_range(start, end).strftime("%Y-%m-%d").tolist()
        missing = set(expected_dates) - set(found_dates)
        raise ValueError(
            f"❌ 日期不完整！在 {start.strftime('%Y-%m-%d')} 至 {end.strftime('%Y-%m-%d')} 区间内：\n"
            f"   - 应有 7 天，实际找到 {len(found_dates)} 天\n"
            f"   - 缺失日期: {sorted(list(missing))}"
        )
    return result


def calculate_port_totals(df):
    arrival = df[df["Arrival / Departure"] == "Arrival"]
    departure = df[df["Arrival / Departure"] == "Departure"]

    mainland = arrival.groupby("Control Point")["Mainland Visitors"].sum()
    local = departure.groupby("Control Point")["Hong Kong Residents"].sum()

    result = pd.concat(
        [mainland.rename("Mainland Arrivals"), local.rename("Local Departures")],
        axis=1,
    )
    return result.fillna(0).reset_index()


def apply_mapping(df):
    mapping = pd.read_excel(MAPPING_FILE)
    required = ["Control Point", "Display Name", "Group"]
    missing = [x for x in required if x not in mapping.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    df = df.merge(mapping, on="Control Point", how="left")
    df["Display Name"] = df["Display Name"].fillna(df["Control Point"])
    df["Group"] = df["Group"].fillna("Other")
    return df


def merge_other(df):
    keep = ["HK-SZ", "Rail", "Airport", "Bridge"]
    main = df[df["Group"].isin(keep)].copy()
    other = df[~df["Group"].isin(keep)].copy()

    if other.empty:
        return main

    other_row = pd.DataFrame(
        [
            {
                "Control Point": "Other",
                "Display Name": "Other",
                "Group": "Other",
                "Mainland Arrivals": other["Mainland Arrivals"].sum(),
                "Local Departures": other["Local Departures"].sum(),
            }
        ]
    )
    return pd.concat([main, other_row], ignore_index=True)


def merge_current_previous(current, previous):
    previous = previous.rename(
        columns={
            "Mainland Arrivals": "Previous Mainland Arrivals",
            "Local Departures": "Previous Local Departures",
        }
    )
    previous = previous[["Display Name", "Previous Mainland Arrivals", "Previous Local Departures"]]
    result = current.merge(previous, on="Display Name", how="outer")

    for col in ["Mainland Arrivals", "Local Departures", "Previous Mainland Arrivals", "Previous Local Departures"]:
        result[col] = result[col].fillna(0)

    return result


def calculate_metrics(df):
    total_arrival = df["Mainland Arrivals"].sum()
    total_departure = df["Local Departures"].sum()

    df["Arrival Share"] = df["Mainland Arrivals"] / total_arrival if total_arrival > 0 else 0
    df["Departure Share"] = df["Local Departures"] / total_departure if total_departure > 0 else 0

    df["Arrival WoW %"] = np.where(
        df["Previous Mainland Arrivals"] == 0,
        0,
        (df["Mainland Arrivals"] - df["Previous Mainland Arrivals"]) / df["Previous Mainland Arrivals"],
    )

    df["Departure WoW %"] = np.where(
        df["Previous Local Departures"] == 0,
        0,
        (df["Local Departures"] - df["Previous Local Departures"]) / df["Previous Local Departures"],
    )

    ordered_cols = [
        "Group",
        "Display Name",
        "Mainland Arrivals",
        "Arrival Share",
        "Arrival WoW %",
        "Local Departures",
        "Departure Share",
        "Departure WoW %",
        "Previous Mainland Arrivals",
        "Previous Local Departures",
    ]
    return df[ordered_cols]


def sort_report(df):
    group_order = {"HK-SZ": 1, "Rail": 2, "Airport": 2, "Bridge": 2, "Other": 3}
    df["Group Order"] = df["Group"].map(group_order)

    return (
        df.sort_values(["Group Order", "Arrival Share"], ascending=[True, False])
        .drop(columns="Group Order")
        .reset_index(drop=True)
    )


def add_total(df):
    prev_mainland_sum = df["Previous Mainland Arrivals"].sum()
    prev_local_sum = df["Previous Local Departures"].sum()

    arrival_wow = (
        (df["Mainland Arrivals"].sum() - prev_mainland_sum) / prev_mainland_sum
        if prev_mainland_sum != 0 else 0.0
    )
    departure_wow = (
        (df["Local Departures"].sum() - prev_local_sum) / prev_local_sum
        if prev_local_sum != 0 else 0.0
    )

    total = pd.DataFrame(
        [
            {
                "Group": "Grand Total",
                "Display Name": "Grand Total",
                "Mainland Arrivals": df["Mainland Arrivals"].sum(),
                "Arrival Share": np.nan,
                "Arrival WoW %": arrival_wow,
                "Local Departures": df["Local Departures"].sum(),
                "Departure Share": np.nan,
                "Departure WoW %": departure_wow,
                "Previous Mainland Arrivals": prev_mainland_sum,
                "Previous Local Departures": prev_local_sum,
            }
        ]
    )
    return pd.concat([df, total], ignore_index=True)


# =====================================================
# OpenPyXL Styling & Formatting Functions
# =====================================================
def get_openpyxl_percentage_format(val):
    if val == 0 or val is None or np.isnan(val):
        return '0%'

    abs_val = abs(val)
    decimals = 0
    while decimals <= 6:
        formatted_str = f"{abs_val * 100:.{decimals}f}%"
        if float(formatted_str.replace("%", "")) != 0:
            break
        decimals += 1

    if decimals == 0:
        return '0%'
    else:
        return '0.' + ('0' * decimals) + '%'


def export_styled_excel(df, weeks, output_file):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Weekly Report"

    font_family = "Arial"
    
    header_dark_fill = PatternFill(start_color="1E5631", end_color="1E5631", fill_type="solid")
    header_light_fill = PatternFill(start_color="D9EAD3", end_color="D9EAD3", fill_type="solid")
    audit_fill = PatternFill(start_color="F3F3F3", end_color="F3F3F3", fill_type="solid")

    font_white_bold = Font(name=font_family, size=11, bold=True, color="FFFFFF")
    font_bold = Font(name=font_family, size=10, bold=True)
    font_regular = Font(name=font_family, size=10)
    
    font_blue_bold = Font(name=font_family, size=10, bold=True, color="0000FF")
    font_blue_regular = Font(name=font_family, size=10, color="0000FF")
    font_red_bold = Font(name=font_family, size=10, bold=True, color="FF0000")
    font_red_regular = Font(name=font_family, size=10, color="FF0000")

    thin_border_side = Side(style="thin", color="D3D3D3")
    border_all_thin = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)

    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")

    # 1. Row 1 日期标题与大表头
    date_str = f"{weeks['current_start'].strftime('%d/%m/%Y')} - {weeks['current_end'].strftime('%d/%m/%Y')}"
    ws["A1"] = date_str
    ws["A1"].font = Font(name=font_family, size=11, bold=True)
    ws.merge_cells("A1:B1")

    ws["C1"] = "Mainland Arrivals"
    ws["F1"] = "Local Departures"
    ws["I1"] = "Audit Data (Previous Week)"

    ws.merge_cells("C1:E1")
    ws.merge_cells("F1:H1")
    ws.merge_cells("I1:J1")

    for col_idx in range(3, 11):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_dark_fill if col_idx <= 8 else audit_fill
        cell.alignment = align_center
        cell.font = font_white_bold if col_idx <= 8 else font_bold

    # 2. Row 2 子表头
    sub_headers = [
        "Port", "",
        "Weekly Total", "% Share", "WoW %",
        "Weekly Total", "% Share", "WoW %",
        "Prev Mainland", "Prev Local"
    ]
    ws.append(sub_headers)
    ws.merge_cells("A2:B2")
    
    for col_idx in range(1, 11):
        cell = ws.cell(row=2, column=col_idx)
        cell.fill = header_light_fill if col_idx <= 8 else audit_fill
        cell.font = font_bold
        cell.alignment = align_center

    # 3. 写入数据行
    for row_idx, row_data in enumerate(df.to_dict("records"), start=3):
        is_total_row = (row_data["Group"] == "Grand Total")
        
        ws.cell(row=row_idx, column=1, value=row_data["Group"])
        ws.cell(row=row_idx, column=2, value=row_data["Display Name"])
        
        ws.cell(row=row_idx, column=3, value=row_data["Mainland Arrivals"])
        ws.cell(row=row_idx, column=4, value=row_data["Arrival Share"])
        ws.cell(row=row_idx, column=5, value=row_data["Arrival WoW %"])
        
        ws.cell(row=row_idx, column=6, value=row_data["Local Departures"])
        ws.cell(row=row_idx, column=7, value=row_data["Departure Share"])
        ws.cell(row=row_idx, column=8, value=row_data["Departure WoW %"])
        
        ws.cell(row=row_idx, column=9, value=row_data["Previous Mainland Arrivals"])
        ws.cell(row=row_idx, column=10, value=row_data["Previous Local Departures"])

        for col_idx in range(1, 11):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.border = border_all_thin
            cell.font = font_bold if is_total_row else font_regular
            cell.alignment = align_left if col_idx <= 2 else align_center

            if col_idx in [3, 6, 9, 10]:
                cell.number_format = "#,##0"
            elif col_idx in [4, 7]:
                val = cell.value
                if is_total_row or val is None or np.isnan(val):
                    cell.value = "-"
                    cell.number_format = '@'
                else:
                    cell.value = float(val)
                    cell.number_format = get_openpyxl_percentage_format(val)
            elif col_idx in [5, 8]:
                val = cell.value
                if val is not None and not np.isnan(val):
                    val_float = float(val)
                    cell.value = val_float
                    num_format_str = get_openpyxl_percentage_format(val_float)

                    if val_float == 0:
                        cell.number_format = num_format_str
                        cell.font = font_bold if is_total_row else font_regular
                    elif val_float > 0:
                        cell.number_format = f'"↑"{num_format_str}'
                        cell.font = font_blue_bold if is_total_row else font_blue_regular
                    else:
                        cell.number_format = f';"↓"{num_format_str}'
                        cell.font = font_red_bold if is_total_row else font_red_regular

    # 4. 合并单元格
    hksz_rows = [r for r in range(3, len(df) + 3) if ws.cell(row=r, column=1).value == "HK-SZ"]
    if hksz_rows:
        min_r, max_r = min(hksz_rows), max(hksz_rows)
        ws.merge_cells(start_row=min_r, start_column=1, end_row=max_r, end_column=1)
        ws.cell(row=min_r, column=1, value="HK - SZ ports").alignment = align_center

    for r in range(3, len(df) + 3):
        grp = ws.cell(row=r, column=1).value
        if grp in ["Rail", "Airport", "Bridge", "Other", "Grand Total"]:
            disp_name = ws.cell(row=r, column=2).value
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
            cell = ws.cell(row=r, column=1)
            cell.value = "Total" if grp == "Grand Total" else disp_name
            cell.alignment = align_left
            if grp == "Grand Total":
                cell.font = font_bold

    # 5. 自适应列宽
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if cell.row == 1:
                continue
            cell_len = sum(2 if ord(char) > 127 else 1 for char in val_str)
            max_len = max(max_len, cell_len)
        ws.column_dimensions[col_letter].width = max(max_len + 4, 10)

    wb.save(output_file)


# =====================================================
# 方案 A：全历史动态 HTML Dashboard 导出模块
# =====================================================
def get_processed_weeks_history(df):
    """提取 CSV 内部所有的完整/非完整历史周切片"""
    df_dates = pd.DataFrame({"Date": df["Date"].unique()}).sort_values("Date")
    df_dates["Week_Start"] = df_dates["Date"].apply(lambda d: d - pd.Timedelta(days=d.weekday()))
    df_dates["Week_End"] = df_dates["Week_Start"] + pd.Timedelta(days=6)
    
    week_stats = df_dates.groupby(["Week_Start", "Week_End"])["Date"].agg(["min", "max", "count"]).reset_index()
    week_stats = week_stats.rename(columns={"count": "Days_Count", "min": "Actual_Min", "max": "Actual_Max"})
    week_stats = week_stats.sort_values("Week_Start", ascending=False).reset_index(drop=True)
    week_stats["Is_Complete"] = week_stats["Days_Count"] == 7
    return week_stats


def generate_interactive_html(df_raw, target_weeks, html_output_file):
    print("⏳ 正在实时计算全历史周报数据，准备构建动态 Dashboard...")
    week_stats = get_processed_weeks_history(df_raw)
    all_data_payload = {}
    
    # 计算初始默认选中的 Key
    default_key = f"{target_weeks['current_start'].strftime('%Y-%m-%d')} ~ {target_weeks['current_end'].strftime('%Y-%m-%d')}"

    for idx in range(len(week_stats)):
        base_row = week_stats.iloc[idx]
        b_start = base_row['Week_Start']
        b_end = base_row['Actual_Max']
        b_days = base_row['Days_Count']
        
        comp_idx = min(idx + 1, len(week_stats) - 1)
        comp_row = week_stats.iloc[comp_idx]
        c_start = comp_row['Week_Start']
        c_cutoff = c_start + pd.Timedelta(days=b_days - 1)

        base_sub = filter_week(df_raw, b_start, b_end) if b_days == 7 else df_raw[(df_raw["Date"] >= b_start) & (df_raw["Date"] <= b_end)]
        comp_sub = df_raw[(df_raw["Date"] >= c_start) & (df_raw["Date"] <= c_cutoff)]

        # 复用核心 pipeline 计算当周表
        curr_p = merge_other(apply_mapping(calculate_port_totals(base_sub)))
        prev_p = merge_other(apply_mapping(calculate_port_totals(comp_sub)))
        rep_df = add_total(sort_report(calculate_metrics(merge_current_previous(curr_p, prev_p))))

        # 每日对比趋势（将 Date 转为字符串格式支持 JSON）
        def get_daily_trend(df_sub, label):
            arr = df_sub[df_sub["Arrival / Departure"] == "Arrival"].groupby("Date")["Mainland Visitors"].sum().reset_index()
            dep = df_sub[df_sub["Arrival / Departure"] == "Departure"].groupby("Date")["Hong Kong Residents"].sum().reset_index()
            m = pd.merge(arr, dep, on="Date")
            m["DayOfWeek"] = m["Date"].dt.dayofweek
            m["Period"] = label
            m["Date"] = m["Date"].dt.strftime("%Y-%m-%d")
            return m

        overlay = pd.concat([get_daily_trend(base_sub, "Base Week"), get_daily_trend(comp_sub, "Comparison Week")]).sort_values("DayOfWeek")
        day_map = {0: 'Mon', 1: 'Tue', 2: 'Wed', 3: 'Thu', 4: 'Fri', 5: 'Sat', 6: 'Sun'}
        overlay['DayLabel'] = overlay['DayOfWeek'].map(day_map)

        key = f"{b_start.strftime('%Y-%m-%d')} ~ {b_end.strftime('%Y-%m-%d')}"
        if not base_row["Is_Complete"]:
            key += f" [Partial: {b_days} days]"

        all_data_payload[key] = {
            "base_date_str": f"{b_start.strftime('%d/%m/%Y')} - {b_end.strftime('%d/%m/%Y')}",
            "comp_date_str": f"{c_start.strftime('%d/%m/%Y')} - {c_cutoff.strftime('%d/%m/%Y')}",
            "report_table": rep_df.to_dict(orient="records"),
            "daily_overlay": overlay.to_dict(orient="records")
        }

    # 全历史 Daily Macro 折线图数据
    df_all_arr = df_raw[df_raw["Arrival / Departure"] == "Arrival"].groupby("Date")["Mainland Visitors"].sum().reset_index()
    df_all_dep = df_raw[df_raw["Arrival / Departure"] == "Departure"].groupby("Date")["Hong Kong Residents"].sum().reset_index()
    df_macro = pd.merge(df_all_arr, df_all_dep, on="Date").sort_values("Date")
    df_macro["DateStr"] = df_macro["Date"].dt.strftime('%Y-%m-%d')

    fig_macro = px.line(
        df_macro, x="DateStr", y=["Mainland Visitors", "Hong Kong Residents"],
        title="Full Historical Daily Traffic Trends",
        color_discrete_map={"Mainland Visitors": "#1E5631", "Hong Kong Residents": "#2B5B84"}
    )
    fig_macro.update_xaxes(rangeslider_visible=True)
    fig_macro.update_layout(height=400, hovermode="x unified", margin=dict(t=40, b=20, l=40, r=20))
    macro_html = fig_macro.to_html(full_html=False, include_plotlyjs='cdn')

    # 动态网页 HTML 架构
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Hong Kong Tourism Interactive Dashboard</title>
        <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background-color: #f8f9fa; margin: 0; padding: 20px; }}
            .container {{ max-width: 1250px; margin: 0 auto; }}
            .header-bar {{ display: flex; justify-content: space-between; align-items: center; background: white; padding: 15px 24px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 20px; border: 1px solid #e9ecef; }}
            h1 {{ color: #1E5631; margin: 0; font-size: 22px; }}
            select {{ padding: 8px 12px; font-size: 14px; border-radius: 6px; border: 1px solid #ced4da; outline: none; background-color: #f1f3f5; font-weight: bold; cursor: pointer; }}
            .card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); margin-bottom: 20px; border: 1px solid #e9ecef; }}
            .date-info {{ font-weight: bold; color: #1E5631; margin-bottom: 12px; font-size: 14px; }}
            .report-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
            .report-table th {{ background-color: #1E5631; color: white; padding: 10px; text-align: right; }}
            .report-table th:nth-child(1), .report-table th:nth-child(2) {{ text-align: left; }}
            .report-table td {{ padding: 8px 10px; border-bottom: 1px solid #e9ecef; text-align: right; }}
            .report-table td:nth-child(1), .report-table td:nth-child(2) {{ text-align: left; }}
            .report-table tr:hover {{ background-color: #f1f3f5; }}
            .report-table .total-row {{ font-weight: bold; background-color: #e8f5e9 !important; border-top: 2px solid #1E5631; border-bottom: 2px solid #1E5631; }}
            .wow-up {{ color: #0000FF; font-weight: bold; }}
            .wow-down {{ color: #FF0000; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header-bar">
                <h1>🇭🇰 Hong Kong Tourism Interactive Dashboard</h1>
                <div>
                    <label for="weekSelector"><b>📅 切换周报 Period: </b></label>
                    <select id="weekSelector" onchange="renderDashboard()"></select>
                </div>
            </div>
            
            <div class="card">
                <div id="dateBanner" class="date-info"></div>
                <div style="overflow-x:auto;">
                    <table class="report-table">
                        <thead>
                            <tr>
                                <th>Group</th><th>Display Name</th>
                                <th>Mainland Arrivals</th><th>Arrival Share</th><th>Arrival WoW %</th>
                                <th>Local Departures</th><th>Departure Share</th><th>Departure WoW %</th>
                            </tr>
                        </thead>
                        <tbody id="tableBody"></tbody>
                    </table>
                </div>
            </div>

            <div class="card"><div id="chartMainland"></div></div>
            <div class="card"><div id="chartLocal"></div></div>
            <div class="card">{macro_html}</div>
        </div>

        <script>
            const payload = {json.dumps(all_data_payload, ensure_ascii=False)};
            const defaultKey = "{default_key}";
            const selector = document.getElementById("weekSelector");

            Object.keys(payload).forEach(function(key) {{
                let opt = document.createElement("option");
                opt.value = key;
                opt.innerText = key;
                if (key.indexOf(defaultKey) !== -1) {{
                    opt.selected = true;
                }}
                selector.appendChild(opt);
            }});

            function renderDashboard() {{
                const selectedKey = selector.value;
                const data = payload[selectedKey];

                document.getElementById("dateBanner").innerHTML = 
                    '📅 Base Period: <span style="color:#000;">' + data.base_date_str + '</span> | Comparison Period (Audit): <span style="color:#000;">' + data.comp_date_str + '</span>';

                let htmlRows = "";
                data.report_table.forEach(function(row) {{
                    const isTotal = (row["Group"] === "Grand Total" || row["Group"] === "Total");
                    const trClass = isTotal ? ' class="total-row"' : '';
                    
                    const arrVal = row['Mainland Arrivals'] !== null ? row['Mainland Arrivals'].toLocaleString() : "-";
                    const arrShare = (row['Arrival Share'] !== null && !isNaN(row['Arrival Share'])) ? (row['Arrival Share'] * 100).toFixed(1) + "%" : "-";
                    
                    let arrWow = "-";
                    if (row['Arrival WoW %'] !== null && !isNaN(row['Arrival WoW %'])) {{
                        const v = row['Arrival WoW %'];
                        if (v > 0) arrWow = '<span class="wow-up">↑ ' + (Math.abs(v) * 100).toFixed(1) + '%</span>';
                        else if (v < 0) arrWow = '<span class="wow-down">↓ ' + (Math.abs(v) * 100).toFixed(1) + '%</span>';
                        else arrWow = (v * 100).toFixed(1) + "%";
                    }}

                    const depVal = row['Local Departures'] !== null ? row['Local Departures'].toLocaleString() : "-";
                    const depShare = (row['Departure Share'] !== null && !isNaN(row['Departure Share'])) ? (row['Departure Share'] * 100).toFixed(1) + "%" : "-";
                    
                    let depWow = "-";
                    if (row['Departure WoW %'] !== null && !isNaN(row['Departure WoW %'])) {{
                        const v = row['Departure WoW %'];
                        if (v > 0) depWow = '<span class="wow-up">↑ ' + (Math.abs(v) * 100).toFixed(1) + '%</span>';
                        else if (v < 0) depWow = '<span class="wow-down">↓ ' + (Math.abs(v) * 100).toFixed(1) + '%</span>';
                        else depWow = (v * 100).toFixed(1) + "%";
                    }}

                    htmlRows += '<tr' + trClass + '>' +
                        '<td>' + row["Group"] + '</td><td>' + row["Display Name"] + '</td>' +
                        '<td>' + arrVal + '</td><td>' + arrShare + '</td><td>' + arrWow + '</td>' +
                        '<td>' + depVal + '</td><td>' + depShare + '</td><td>' + depWow + '</td>' +
                    '</tr>';
                }});
                document.getElementById("tableBody").innerHTML = htmlRows;

                const categories = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
                
                function buildPlotData(keyField) {{
                    let baseVals = [], compVals = [], baseTexts = [], compTexts = [];
                    categories.forEach(function(day) {{
                        let bItem = data.daily_overlay.find(function(d) {{ return d.DayLabel === day && d.Period === "Base Week"; }});
                        let cItem = data.daily_overlay.find(function(d) {{ return d.DayLabel === day && d.Period === "Comparison Week"; }});
                        
                        let bv = bItem ? bItem[keyField] : 0;
                        let cv = cItem ? cItem[keyField] : 0;
                        
                        baseVals.push(bv);
                        compVals.push(cv);
                        baseTexts.push(bv >= 1000 ? (bv/1000).toFixed(1) + 'k' : bv.toString());
                        compTexts.push(cv >= 1000 ? (cv/1000).toFixed(1) + 'k' : cv.toString());
                    }});

                    return {{
                        baseTrace: {{ x: categories, y: baseVals, text: baseTexts, textposition: 'outside', name: 'Base Week', type: 'bar', marker: {{ color: keyField === 'Mainland Visitors' ? '#1E5631' : '#2B5B84' }} }},
                        compTrace: {{ x: categories, y: compVals, text: compTexts, textposition: 'outside', name: 'Comparison Week', type: 'bar', marker: {{ color: keyField === 'Mainland Visitors' ? '#A2C4C9' : '#90B4CE' }} }}
                    }};
                }}

                const mData = buildPlotData('Mainland Visitors');
                Plotly.newPlot('chartMainland', [mData.baseTrace, mData.compTrace], {{
                    title: 'Mainland Arrival Daily Comparison',
                    barmode: 'group',
                    height: 350,
                    margin: {{ t: 40, b: 30, l: 50, r: 20 }}
                }}, {{responsive: true}});

                const lData = buildPlotData('Hong Kong Residents');
                Plotly.newPlot('chartLocal', [lData.baseTrace, lData.compTrace], {{
                    title: 'Local Departure Daily Comparison',
                    barmode: 'group',
                    height: 350,
                    margin: {{ t: 40, b: 30, l: 50, r: 20 }}
                }}, {{responsive: true}});
            }}

            renderDashboard();
        </script>
    </body>
    </html>
    """

    with open(html_output_file, "w", encoding="utf-8") as f:
        f.write(html_template)

    print(f"✅ 动态 HTML Dashboard 已生成: {html_output_file.name}")


# =====================================================
# Main Pipeline Exec & SOP Checks
# =====================================================
def generate_report(raw, weeks):
    current = filter_week(raw, weeks["current_start"], weeks["current_end"])
    previous = filter_week(raw, weeks["previous_start"], weeks["previous_end"])

    current = calculate_port_totals(current)
    previous = calculate_port_totals(previous)

    current = apply_mapping(current)
    previous = apply_mapping(previous)

    current = merge_other(current)
    previous = merge_other(previous)

    report = merge_current_previous(current, previous)
    report = calculate_metrics(report)
    report = sort_report(report)
    report = add_total(report)

    return report


def run_sop_checks(df):
    data_rows = df[df["Group"] != "Grand Total"]
    total_row = df[df["Group"] == "Grand Total"].iloc[0]

    # 1. 校验人次总分勾稽
    mainland_sum = data_rows["Mainland Arrivals"].sum()
    assert mainland_sum == total_row["Mainland Arrivals"], \
        f" [SOP 失败] Mainland Arrivals 加总 ({mainland_sum}) 与 Total 行 ({total_row['Mainland Arrivals']}) 不匹配！"

    local_sum = data_rows["Local Departures"].sum()
    assert local_sum == total_row["Local Departures"], \
        f" [SOP 失败] Local Departures 加总 ({local_sum}) 与 Total 行 ({total_row['Local Departures']}) 不匹配！"

    # 2. 校验 Share 占比归一
    arrival_share_sum = data_rows["Arrival Share"].sum()
    assert abs(arrival_share_sum - 1.0) < 1e-5, \
        f" [SOP 失败] Mainland Arrival Share 相加等于 {arrival_share_sum:.4f}，未达到 100%！"

    departure_share_sum = data_rows["Departure Share"].sum()
    assert abs(departure_share_sum - 1.0) < 1e-5, \
        f" [SOP 失败] Local Departure Share 相加等于 {departure_share_sum:.4f}，未达到 100%！"

    # 3. 校验关键列是否存在空值 (NaN)
    check_cols = ["Mainland Arrivals", "Local Departures", "Arrival Share", "Departure Share", "Arrival WoW %", "Departure WoW %"]
    for col in check_cols:
        nan_count = data_rows[col].isna().sum()
        assert nan_count == 0, f" [SOP 失败] 数据列 '{col}' 中发现了 {nan_count} 个空值 (NaN)！"

    print(" [SOP 校验通过] 数据逻辑完美，准备导出 Excel 与 HTML 报表...")


# =====================================================
# Main 运行入口
# =====================================================
if __name__ == "__main__":
    # 1. 自动从网络/本地更新 Raw Data
    raw_csv_path = fetch_latest_immd_data(output_dir=INPUT_DIR)
    
    # 2. 加载原始数据并定位目标周
    raw = load_data()
    weeks = get_complete_week(raw, target_date_str=TARGET_DATE)

    # 3. 运行主 Pipeline 与 SOP 校验
    report = generate_report(raw, weeks)
    run_sop_checks(report)

    # 4. 导出 Excel 报表与归档
    start_str = weeks["current_start"].strftime("%Y%m%d")
    end_str = weeks["current_end"].strftime("%Y%m%d")
    year_str = weeks["current_start"].strftime("%Y")

    archive_dir = OUTPUT_DIR / "archive" / year_str
    archive_dir.mkdir(parents=True, exist_ok=True)

    latest_file = OUTPUT_DIR / "latest_weekly_report.xlsx"
    archive_file = archive_dir / f"{start_str}_{end_str}.xlsx"

    export_styled_excel(report, weeks, latest_file)
    shutil.copy(latest_file, archive_file)

    print(f"🎉 最新 Excel 报表已生成: {latest_file.name}")
    print(f"📦 历史 Excel 已归档至: {archive_file.relative_to(BASE_DIR)}")

    # 5. 生成方案 A 交互式 HTML Dashboard 并自动弹出打开
    html_file = OUTPUT_DIR / "Hong_Kong_Tourism_Dashboard.html"
    generate_interactive_html(raw, weeks, html_file)
    
    # 自动在默认浏览器中打开交互仪表盘
    webbrowser.open(html_file.as_uri())