# 自動化情資管線專案 - 5 分鐘上手

> 本專案每天自動從 RSS/Atom feeds 收集技術資訊，產生摘要報告。

## 🚀 快速開始（5 分鐘）

### 1️⃣ 安裝環境（1 分鐘）

```bash
# 確認 Python 版本 >= 3.10
python --version

# 安裝依賴
pip install -r requirements.txt
```

### 2️⃣ 設定資料來源（2 分鐘）

編輯 `ops/feeds.yml` 新增你要的來源：

```yaml
sources:
  - name: "Hacker News"
    url: "https://news.ycombinator.com/rss"
    type: "rss"
    tags: ["tech", "startup"]
    enabled: true
    
  - name: "我的自訂 Feed"
    url: "https://example.com/feed.xml"  # 改成你的 RSS URL
    type: "rss"
    tags: ["custom"]
    enabled: true
```

### 3️⃣ 執行摘要腳本（1 分鐘）

```bash
# 預覽模式（不寫檔案）
python ops/digest.py --dry-run

# 實際產生摘要
python ops/digest.py

# 產生指定日期的摘要
python ops/digest.py --date 2025-12-20

# 查看輸出
cat out/digest-2025-12-22.md
cat logs/digest-2025-12-22.log
```

### 4️⃣ 開 Issue 追蹤任務（1 分鐘）

1. 前往 GitHub Issues 頁面
2. 點擊「New Issue」
3. 選擇模板：
   - **Intel Digest**：每日資訊摘要任務
   - **Dev Task**：開發/修 bug 任務
4. 填寫表單，送出

### 5️⃣ 提交 PR（選用）

1. 建立分支：
   ```bash
   git checkout -b feat/my-feature
   ```

2. 修改檔案並提交：
   ```bash
   git add ops/feeds.yml
   git commit -m "feat(feeds): 新增 Example RSS 來源"
   ```

3. 推送並開 PR：
   ```bash
   git push origin feat/my-feature
   # 前往 GitHub 開 Pull Request
   ```

4. PR 會自動套用模板，填寫即可

---

## 📁 專案結構

```
agrnt/
├── AGENTS.md          # AI Agent 規範與工作流程
├── SPEC.md            # 技術規格與系統設計
├── README.md          # 本檔案
├── requirements.txt   # Python 依賴清單
├── .gitignore         # Git 排除設定
├── ops/
│   ├── feeds.yml      # RSS/Atom 資料來源設定
│   └── digest.py      # 主要執行腳本
├── out/               # 輸出目錄（自動建立）
│   └── digest-*.md
├── logs/              # 日誌目錄（自動建立）
│   └── digest-*.log
└── .github/
    ├── ISSUE_TEMPLATE/
    │   ├── 01-intel-digest.yml    # Intel Digest 模板
    │   └── 02-dev-task.yml        # Dev Task 模板
    ├── pull_request_template.md   # PR 模板
    └── workflows/
        └── daily-intel-issue.yml  # 每日自動開 Issue
```

## 🔧 進階設定

### 自動排程

`.github/workflows/daily-intel-issue.yml` 會在每天 **09:00 (Asia/Taipei)** 自動開 Issue。

要修改時間，編輯 cron 表達式：
```yaml
schedule:
  - cron: "0 1 * * *"  # 01:00 UTC = 09:00 Asia/Taipei
```

### GitHub Secrets

如需啟用自動化功能，設定以下 Secrets：
- `GITHUB_TOKEN`：自動提供，用於開 Issue

### 測試覆蓋率（未來）

執行測試（需先建立 `tests/`）：
```bash
pytest tests/ --cov=ops --cov-report=html
```

---

## 📖 延伸閱讀

- [AGENTS.md](AGENTS.md) - 完整 Agent 規範、Commit 格式、DoD
- [SPEC.md](SPEC.md) - 系統架構、失敗處理、驗收標準
- [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) - 專案完整分析報告

## 🤝 貢獻指南

請遵循 [AGENTS.md](AGENTS.md) 中的規範：
- ✅ Commit 使用 **Conventional Commits** 格式
- ✅ PR 必須關聯 **Issue**（使用 `Closes #123`）
- ✅ 程式碼必須通過 **Black** 格式化
- ✅ 必須包含 **type hints**
- ❌ **絕對不要**提交 `.env` 檔案

## 📝 授權

MIT License
