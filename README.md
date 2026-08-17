# 🇭🇰 香港出入境旅客流量周报自动化系统 (HK Tourism Report Automation)

自动从香港政府公开数据源（data.gov.hk）抓取每日出入境旅客流量数据，进行数据清洗、SOP 逻辑校验，并生成格式化的 Excel 周报。

---

## 📂 项目目录结构
```text
HK_Tourism_Report/
├── input/                      # 存放下载的原始 CSV（受 .gitignore 忽略）
├── output/                     # 存放生成的 Excel 报表
│   └── archive/                # 历史周报按年份归档目录
├── template/                   # 静态配置文件（port_mapping.xlsx）
├── download_data.py            # 模块 1：数据抓取与反缓存校验
├── weekly_report_data.py       # 模块 2：数据处理、SOP 检查与 Excel 渲染
├── dashboard.py                # 模块 3：数据可视化
├── CHANGELOG.md                # 项目开发日志与版本变更记录
├── .gitignore                  # Git 忽略规则
└── README.md                   # 本说明文档

## 🔄 每日/每周工作流程 (SOP)
### 1. 准备工作（换电脑/新一周）
- 打开 VS Code，选择终端。
- 拉取云端最新代码：
  ```bash
  git pull origin main

### 2. 运行报表生成，执行主程序（自动下载最新数据并处理）
  ```bash
  python weekly_report_data.py

### 3. 数据复核与产出
- 最新报表：查看 output/latest_weekly_report.xlsx。
- 历史归档：确认已自动归档至 output/archive/YYYY/。

### 4. 提交代码变更（仅在修改了 .py 脚本后）
- 提交并推送至 GitHub：
  ```bash
  git add download_data.py weekly_report_data.py
  git commit -m "feat: 更新数据处理逻辑"
  git push origin main
