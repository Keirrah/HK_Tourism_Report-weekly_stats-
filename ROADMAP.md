# 🇭🇰 HK Tourism Report Automation - Roadmap & Status

Tracked features, implementations, and Git / VS Code revision guide.

---

## ✅ Completed Implementations

* **Strict 2-File Input Backup Strategy**  
  * `download_data.py` now automatically copies the previous `latest_immd_raw.csv` to `backup_immd_raw.csv` before saving new data.  
  * Your `input/` folder will always contain strictly **2 files**: the current data and the previous backup.
* **Single-Point Date Format Normalization**  
  * Added `clean_and_parse_dates()` in `download_data.py` and imported it into `weekly_report_data.py`.  
  * Normalizes `/` to `-`, parses day-first (`%d-%m-%Y`) and ISO (`%Y-%m-%d`), and raises a clear error if malformed dates are detected (eliminating silent row drops).
* **Git Ignore Setup**  
  * Added `.gitignore` to keep raw CSV downloads (`input/`), compiled cache (`__pycache__/`), and system files (`.DS_Store`) out of Git repository tracking.

---

## 🚧 Upcoming Visual & Dashboard Features

1. **Stacked Bar Charts for Port Contributions**  
   * Upgrade daily & weekly port breakdown charts from grouped bars to stacked bars (or 100% share bars) in `dashboard.py` and `weekly_report_data.py` to highlight port contributions (HK-SZ land ports, Rail, Airport, Bridge, Other).
2. **Annotated Historical Trend Line**  
   * Set trend line starting view from 2023 (post-reopening) and add visual annotations for key events:
     * **Chinese Public Holidays**: May Day Golden Week, National Day Golden Week (Oct 1), Chinese New Year / Spring Festival.
     * **HK Public Holidays**: Easter, HK SAR Establishment Day (July 1), Christmas.
     * **Port Milestones**: Reopening of Huanggang Port & 24-hour clearance policy milestones.
3. **Extended Economic & Tourism Dashboards**  
   * Add dedicated dashboard tabs for external economic and retail/hotel data tables.

---

## 🛠️ Step-by-Step Guide: Connecting Project to GitHub via VS Code

### Step 1: Open Terminal in VS Code
Open VS Code, press `Ctrl + ~` (or `Cmd + ~` on Mac) to open the built-in terminal, and verify you are in the project folder:
```bash
pwd
# Expected output: /Users/yy/Desktop/HK_Tourism_Report-weekly_stats-
```

### Step 2: Initialize Git Repository
Run the following commands in the terminal:
```bash
git init
git add .
git commit -m "feat: initial commit with date parsing, 2-file backup, and gitignore"
```

### Step 3: Link to Your GitHub Repository
1. Go to [GitHub.com](https://github.com) and click **New Repository**.
2. Name it `HK_Tourism_Report` (set to Private or Public).
3. Copy the repository URL (e.g., `https://github.com/your-username/HK_Tourism_Report.git`).
4. Run in your VS Code terminal:
```bash
git branch -M main
git remote add origin https://github.com/your-username/HK_Tourism_Report.git
git push -u origin main
```

### Step 4: Daily Revision Update Workflow in VS Code
Whenever you make updates to your `.py` files in VS Code:
1. Click the **Source Control** icon on the left sidebar (or press `Ctrl+Shift+G` / `Cmd+Shift+G`).
2. Type a brief commit message in the box (e.g. `update: stacked bar charts`).
3. Click **Commit**, then click **Sync Changes** (or run `git push origin main` in the terminal).
