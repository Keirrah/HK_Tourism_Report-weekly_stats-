#%%
import sys
import subprocess

# 定义你的自动化流程所依赖的所有 Python 包
REQUIRED_PACKAGES = [
    "pandas",
    "openpyxl",
    "numpy",
    "matplotlib",
    "seaborn",
    "requests"
]

def auto_setup_environment(packages):
    """
    自动检测当前电脑的 Python 环境，如缺少第三方包则自动静默安装
    """
    installed_packages = []
    missing_packages = []

    # 1. 检测包是否已安装
    for pkg in packages:
        try:
            __import__(pkg)
            installed_packages.append(pkg)
        except ImportError:
            missing_packages.append(pkg)

    # 2. 如果存在未安装的包，自动通过 pip 安装
    if missing_packages:
        print(f"检测到当前电脑缺少以下程序包: {missing_packages}")
        print("正在为您自动安装，请稍候...\n")
        
        for pkg in missing_packages:
            try:
                # 使用当前 Python 解释器对应的 pip 自动下载并安装
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
# 下面开始正常 import 你的依赖库和主程序代码
# =====================================================

import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from download_data import fetch_latest_immd_data
#%%
# =====================================================
# File path
# =====================================================

BASE_DIR = Path(__file__).resolve().parent

INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
TEMPLATE_DIR = BASE_DIR / "template"

RAW_FILE = INPUT_DIR / "latest_immd_raw.csv"
MAPPING_FILE = TEMPLATE_DIR / "port_mapping.xlsx"

OUTPUT_DIR.mkdir(exist_ok=True)


# =====================================================
# Data Processing Pipeline (Pandas)
# =====================================================

def load_data():
    df = pd.read_csv(RAW_FILE)
    df.columns = df.columns.str.strip()  # 去除列名空格
    
    # 强制按香港本地格式（Day First: 日/月/年）解析日期
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date"])
    
    # 填充与数值格式清洗
    numeric_cols = ["Hong Kong Residents", "Mainland Visitors", "Other Visitors", "Total"]
    for col in numeric_cols:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].astype(str).str.replace(",", "")
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            
    return df


def get_complete_week(df):
    latest_date = df["Date"].max()
    
    # 按照周一到周日对齐自然周
    # latest_date.weekday(): 0=Mon, 6=Sun
    current_week_mon = latest_date - pd.Timedelta(days=latest_date.weekday())
    
    # 若最新一天尚未填满到本周日，则取上一个完整自然周（周一至周日）
    if latest_date < current_week_mon + pd.Timedelta(days=6):
        latest_end = current_week_mon - pd.Timedelta(days=1)   # 上周日
        latest_start = latest_end - pd.Timedelta(days=6)        # 上周一
    else:
        latest_end = current_week_mon + pd.Timedelta(days=6)    # 本周日
        latest_start = current_week_mon                        # 本周一

    previous_end = latest_start - pd.Timedelta(days=1)
    previous_start = previous_end - pd.Timedelta(days=6)

    print(f"📅 [时间窗口校准]")
    print(f"   - 数据最新日期: {latest_date.strftime('%Y-%m-%d')}")
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

    df["Arrival Share"] = df["Mainland Arrivals"] / total_arrival
    df["Departure Share"] = df["Local Departures"] / total_departure

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
                "Arrival Share": np.nan,  # 使用 np.nan 保持数据类型统一
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
# OpenPyXL Styling & Formatting Function (全表 WoW 箭头/动态精度升级版)
# =====================================================

def format_dynamic_percentage(val):
    """
    辅助函数：动态计算百分比保留位数。
    如果保留 0 位小数结果为 0%，但实际不为 0，则递增保留位数直到出现非 0 数字。
    返回: (格式化后的数字字符串, 是否大于0, 是否等于0)
    """
    if val == 0 or val is None:
        return "0%", 0, True

    is_positive = val > 0
    abs_val = abs(val)

    # 从 0 位小数开始尝试
    decimals = 0
    while decimals <= 6:  # 设定最大安全上限防止死循环
        formatted_str = f"{abs_val * 100:.{decimals}f}%"
        # 检查格式化后的数值部分是否非零
        num_part = float(formatted_str.replace("%", ""))
        if num_part != 0:
            break
        decimals += 1

    return formatted_str, is_positive, False


def export_styled_excel(df, weeks, output_file):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Weekly Report"

    font_family = "Arial"
    
    header_dark_fill = PatternFill(start_color="1E5631", end_color="1E5631", fill_type="solid") # 深绿
    header_light_fill = PatternFill(start_color="D9EAD3", end_color="D9EAD3", fill_type="solid") # 浅绿
    audit_fill = PatternFill(start_color="F3F3F3", end_color="F3F3F3", fill_type="solid") # 浅灰
    yellow_fill = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid") # 淡黄背景

    font_white_bold = Font(name=font_family, size=11, bold=True, color="FFFFFF")
    font_bold = Font(name=font_family, size=10, bold=True)
    font_regular = Font(name=font_family, size=10)
    
    # 颜色定义：蓝字与红字
    font_blue_bold = Font(name=font_family, size=10, bold=True, color="0000FF")
    font_blue_regular = Font(name=font_family, size=10, color="0000FF")
    font_red_bold = Font(name=font_family, size=10, bold=True, color="FF0000")
    font_red_regular = Font(name=font_family, size=10, color="FF0000")

    thin_border_side = Side(style="thin", color="D3D3D3")
    thick_border_side = Side(style="medium", color="000000")
    
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


            # 人次格式 (Col 3, 6, 9, 10)
            if col_idx in [3, 6, 9, 10]:
                cell.number_format = "#,##0"

            # Share 格式 (Col 4, 7)
            elif col_idx in [4, 7]:
                val = cell.value
                if is_total_row or val is None:
                    cell.value = "-"
                else:
                    num_str, _, is_zero = format_dynamic_percentage(val)
                    cell.value = num_str

            # WoW % 格式化逻辑 (Col 5, 8) —— 新增加强版
            elif col_idx in [5, 8]:
                val = cell.value
                if val is not None:
                    num_str, is_positive, is_zero = format_dynamic_percentage(val)

                    if is_zero:
                        cell.value = "0%"
                        cell.font = font_bold if is_total_row else font_regular
                    elif is_positive:
                        cell.value = f"↑{num_str}"
                        cell.font = font_blue_bold if is_total_row else font_blue_regular
                    else:
                        cell.value = f"↓{num_str}"
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
# Main Pipeline Exec
# =====================================================

def generate_report():
    raw = load_data()
    weeks = get_complete_week(raw)

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

    return report, weeks

# =====================================================
# SOP 自动化数据断言检查 (SOP Checks)
# =====================================================

def run_sop_checks(df):
    """
    导出前的强制数据关卡，一旦发现逻辑不自洽，直接报错并阻止导出。
    """
    # 拆分数据行与 Total 行
    data_rows = df[df["Group"] != "Grand Total"]
    total_row = df[df["Group"] == "Grand Total"].iloc[0]

    # 1. 校验人次总分勾稽：普通行相加必须严格等于 Total 行
    mainland_sum = data_rows["Mainland Arrivals"].sum()
    assert mainland_sum == total_row["Mainland Arrivals"], \
        f" [SOP 失败] Mainland Arrivals 加总 ({mainland_sum}) 与 Total 行 ({total_row['Mainland Arrivals']}) 不匹配！"

    local_sum = data_rows["Local Departures"].sum()
    assert local_sum == total_row["Local Departures"], \
        f" [SOP 失败] Local Departures 加总 ({local_sum}) 与 Total 行 ({total_row['Local Departures']}) 不匹配！"

    # 2. 校验 Share 占比归一：各口岸占比相加必须等于 100% (允许微小浮点数误差)
    arrival_share_sum = data_rows["Arrival Share"].sum()
    assert abs(arrival_share_sum - 1.0) < 1e-5, \
        f" [SOP 失败] Mainland Arrival Share 相加等于 {arrival_share_sum:.4f}，未达到 100%！"

    departure_share_sum = data_rows["Departure Share"].sum()
    assert abs(departure_share_sum - 1.0) < 1e-5, \
        f" [SOP 失败] Local Departure Share 相加等于 {departure_share_sum:.4f}，未达到 100%！"

    # 3. 校验关键列是否存在空值/非数字 (NaN)
    check_cols = ["Mainland Arrivals", "Local Departures", "Arrival Share", "Departure Share", "Arrival WoW %", "Departure WoW %"]
    for col in check_cols:
        nan_count = data_rows[col].isna().sum()
        assert nan_count == 0, f" [SOP 失败] 数据列 '{col}' 中发现了 {nan_count} 个空值 (NaN)！"

    print(" [SOP 校验通过] 数据逻辑完美，准备导出 Excel 报表...")


# =====================================================
# Main 运行入口
# =====================================================

if __name__ == "__main__":
    raw_csv_path = fetch_latest_immd_data(output_dir=INPUT_DIR)
    report, weeks = generate_report()
    run_sop_checks(report)

    # 1. 计算日期字符串
    start_str = weeks["current_start"].strftime("%Y%m%d")
    end_str = weeks["current_end"].strftime("%Y%m%d")
    year_str = weeks["current_start"].strftime("%Y")

    # 2. 创建按年份归档的子目录: output/archive/2026/
    archive_dir = OUTPUT_DIR / "archive" / year_str
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 3. 定义两个导出路径
    # 路径 A: 永远指向最新报表（方便 Dashboard 或其他工具固定读取）
    latest_file = OUTPUT_DIR / "latest_weekly_report.xlsx"
    
    # 路径 B: 带日期的历史归档报表（方便人工核对与历史留存）
    dated_filename = f"{start_str}_{end_str}.xlsx"
    archive_file = archive_dir / dated_filename

    # 4. 导出最新版文件
    export_styled_excel(report, weeks, latest_file)
    
    # 5. 复制保存一份至历史归档目录
    import shutil
    shutil.copy(latest_file, archive_file)

    print(f"🎉 最新报表已生成: {latest_file.name}")
    print(f"📦 历史报表已归档至: {archive_file.relative_to(BASE_DIR)}")