import sys
import subprocess
import requests
import time
import shutil
from pathlib import Path
import pandas as pd
from datetime import datetime

# 唯一的入境处官方数据下载链接
IMMD_DATA_URL = "https://www.immd.gov.hk/opendata/eng/transport/immigration_clearance/statistics_on_daily_passenger_traffic.csv"

DEFAULT_INPUT_DIR = Path(__file__).parent / "input"
DEFAULT_FILE_NAME = "latest_immd_raw.csv"
BACKUP_FILE_NAME = "backup_immd_raw.csv"


def clean_and_parse_dates(date_series):
    """统一清洗与解析日期，防止混合格式误判"""
    raw_dates = date_series.astype(str).str.strip().str.replace("/", "-")
    parsed_dates = pd.to_datetime(raw_dates, format="%d-%m-%Y", errors="coerce").fillna(
        pd.to_datetime(raw_dates, format="%Y-%m-%d", errors="coerce")
    )
    invalid_count = parsed_dates.isna().sum()
    if invalid_count > 0:
        raise ValueError(f"❌ 检测到 {invalid_count} 行无法解析的日期！")
    return parsed_dates


def fetch_latest_immd_data(output_dir=DEFAULT_INPUT_DIR, filename=DEFAULT_FILE_NAME):
    """
    从 data.gov.hk 下载最新每日出入境流量数据（带反缓存机制 + 自动覆盖备份上版文件）
    """
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / filename
    backup_path = target_dir / BACKUP_FILE_NAME

    # 1. 加上时间戳参数 _t=xxxx，强制绕过 CDN / 网络缓存，获取最新数据
    cache_buster_url = f"{IMMD_DATA_URL}?_t={int(time.time())}"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }

    print(f"🌐 [Downloader] 正在从 data.gov.hk 获取最新数据...")
    print(f"🔗 请求地址: {cache_buster_url}")

    try:
        response = requests.get(cache_buster_url, headers=headers, timeout=20)
        
        if response.status_code == 200:
            # 若已有旧文件，备份为 backup_immd_raw.csv（确保 input/ 下始终只有 2 个 raw CSV）
            if file_path.exists():
                shutil.copy2(file_path, backup_path)
                print(f"📦 [Backup] 已覆盖更新上一版本旧数据备份: {backup_path.resolve()}")

            with open(file_path, "wb") as f:
                f.write(response.content)
            
            # 校验下载下来的 CSV 日期
            df = pd.read_csv(file_path)
            df.columns = df.columns.str.strip()
            df["Date"] = clean_and_parse_dates(df["Date"])
            max_date = df["Date"].max()

            print(f"✅ [Downloader] 下载成功！")
            print(f"   - 保存路径: {file_path.resolve()}")
            print(f"   - 数据最新日期: {max_date.strftime('%Y-%m-%d')}\n")
            return file_path
        else:
            raise RuntimeError(f"服务器响应错误，HTTP 状态码: {response.status_code}")

    except Exception as e:
        print(f"❌ [Downloader] 数据下载失败！原因: {e}")
        if file_path.exists():
            print(f"⚠️ 警告: 将尝试使用本地缓存文件: {file_path}")
            return file_path
        else:
            raise FileNotFoundError("没有找到可用的本地输入文件，程序终止！")


if __name__ == "__main__":
    fetch_latest_immd_data()