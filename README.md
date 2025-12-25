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
   - key: "hacker_news"
      name: "Hacker News"
      url: "https://news.ycombinator.com/rss"
      type: "rss"
      category: "community"
      tags:
         - "tech"
         - "startup"
      limit: 30
      enabled: true

   - key: "producthunt_daily"
      name: "Product Hunt Daily"
      url: "https://api.producthunt.com/v2/api/graphql"
      type: "producthunt"
      category: "product"
      tags:
         - "launch"
         - "startup"
      limit: 20
      enabled: false  # 啟用前請先設定 PRODUCTHUNT_TOKEN
```

> `type` 支援 `rss`、`atom` 與 `producthunt`。`category` 決定 Digest 的分組（例如 `community`、`news`、`product`），`limit` 可以限制每個來源最多抓幾篇文章，預設為 50。

### 3️⃣ 執行 Collector + Digest（2 分鐘）

```bash
# 先收集來源並輸出 JSON（可 dry-run 僅檢查統計）
python ops/collector.py --dry-run
python ops/collector.py --date 2025-12-22

# 再由 JSON 產出 Markdown 摘要
python ops/digest.py --dry-run
python ops/digest.py --date 2025-12-22

# 查看輸出
cat out/raw-2025-12-22.json
cat out/digest-2025-12-22.md
cat logs/collector-2025-12-22.log
cat logs/digest-2025-12-22.log
```

> **推薦排程**：若只是檢查來源設定，可先跑 `--dry-run`；確認無誤後再執行正式產出並推送到 GitHub Actions。

---

### 🔄 典型作業流程（Collector → Digest → Issue）

| 步驟 | 指令 / 說明 | 產物 |
| --- | --- | --- |
| 1. Collector | `python ops/collector.py --date <YYYY-MM-DD>` | `out/raw-YYYY-MM-DD.json`、`logs/collector-YYYY-MM-DD.log` |
| 2. Digest | `python ops/digest.py --date <YYYY-MM-DD>` | `out/digest-YYYY-MM-DD.md`、`logs/digest-YYYY-MM-DD.log` |
| 3. 發佈 Issue | `.github/workflows/daily-intel-issue.yml` 會讀 Markdown 並建立每日 Issue；可透過 `workflow_dispatch` 手動重跑 | GitHub Issue（intel+digest 標籤） |

> **錯誤碼對照**：Collector 1=設定錯誤、2=來源皆失敗、3=寫檔失敗；Digest 1=JSON 解析失敗、2=資料為空、3=寫檔失敗。

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

## 📡 內建資料來源（2025-12）

| key | 來源 | 類型 | 備註 |
| --- | --- | --- | --- |
| `hacker_news` | Hacker News 官方 RSS | RSS | 穩定來源，適合觀察產業 & 工程討論 |
| `github_trending` | GitHubTrendingRSS（第三方） | RSS | GitHub 無官方 RSS，需留意第三方失效，可自行部署 RSSHub 備援 |
| `github_releases_pytorch` / `github_releases_vscode` | GitHub Releases Atom | Atom | 直接使用 `<owner>/<repo>/releases.atom`，最穩定 |
| `huggingface_daily_papers` | Takara AI Papers feed（第三方） | RSS | Hugging Face 無官方 RSS，必要時可自建 scraper |
| `producthunt_daily` | Product Hunt GraphQL API | Custom (`producthunt`) | 需 `PRODUCTHUNT_TOKEN`，若無 token 請保持 disabled |

> 若想加其它 GitHub Releases，只需在 `url` 填入 `https://github.com/<owner>/<repo>/releases.atom` 並複製設定即可。

## 📁 專案結構

```
agrnt/                     # 專案根目錄
├── AGENTS.md              # AI Agent 規範與工作流程
├── SPEC.md                # 系統技術規格與設計細節
├── README.md              # 使用說明與操作指南（本檔）
├── requirements.txt       # Python 依賴套件列表
├── .gitignore             # Git 版本控制忽略規則
├── ops/                   # Collector / Digest 程式與設定
│   ├── feeds.yml          # RSS/Atom/Product Hunt 等來源清單
│   ├── collector.py       # 收集所有來源並產出 raw JSON
│   └── digest.py          # 讀取 raw JSON 生成 Markdown 摘要
├── out/                   # Collector / Digest 的輸出目錄（自動建立）
│   ├── raw-YYYY-MM-DD.json  # 每日原始資料（Collector 輸出）
│   └── digest-YYYY-MM-DD.md # 每日摘要（Digest 輸出，可用於 Issue）
├── logs/                  # Collector / Digest 的執行日誌（自動建立）
│   ├── collector-YYYY-MM-DD.log  # Collector 執行記錄
│   └── digest-YYYY-MM-DD.log     # Digest 執行記錄
└── .github/               # GitHub Workflow 與模板設定
   ├── ISSUE_TEMPLATE/    # GitHub Issue 模板
   │   ├── 01-intel-digest.yml  # 每日情資摘要 Issue 模板
   │   └── 02-dev-task.yml      # 開發 / 修 bug Issue 模板
   ├── pull_request_template.md # Pull Request 模板
   └── workflows/
      └── daily-intel-issue.yml # 每日自動執行 Collector → Digest → Issue 的 CI
```

   ## 🧱 Collector → Digest 資料流程

   1. `ops/collector.py` 讀取 `ops/feeds.yml`，逐一抓取啟用的來源並去重，最後輸出 `out/raw-YYYY-MM-DD.json`。
   2. JSON 結構包含：
      - `meta`：內容品質評估指標（`generated_at`、`raw_entries`、`unique_entries`、`dedup_rate`、`category_counts`、`failed_sources` 等）。
      - `entries`：每筆標準化資料，欄位包含 `source_key`、`source`、`category`、`title`、`url`、`summary_raw`、`published_at`、`fetched_at`、`tags`。
   3. `ops/digest.py` 單純讀 JSON 並輸出 Markdown，會在開頭加入「摘要指標」區塊（去重率、分類筆數、失敗來源）並依 `category`、來源排序分組，過程中完全不再觸網，方便重跑/除錯。

   若 Digest 失敗，只需保留 JSON 即可再次嘗試，不用重抓所有來源。

### 內容品質評估指標

Collector 會在 `meta` 中輸出以下指標，Digest 也會在「摘要指標」章節呈現：
- **去重率 (`dedup_rate`)**：重複連結占原始筆數的比例，便於追蹤來源品質。
- **分類統計 (`category_counts`)**：各 `category` 的每日產出筆數，觀察內容分布。
- **來源健康度 (`failed_sources`)**：當日抓取失敗的來源清單與數量，快速定位異常來源。

這些欄位可以直接由 JSON 推算，也方便後續接入監控或 PROJECT_ANALYSIS 報表。

## 🔧 進階設定

### 自動排程

`.github/workflows/daily-intel-issue.yml` 會在每天 **09:00 (Asia/Taipei)** 自動執行 Collector → Digest，並用 `peter-evans/create-issue-from-file` 將 Markdown 發佈成 Issue。

要修改時間，編輯 cron 表達式：
```yaml
schedule:
  - cron: "0 1 * * *"  # 01:00 UTC = 09:00 Asia/Taipei
```

### GitHub Secrets

如需啟用自動化功能，設定以下 Secrets：
- `GITHUB_TOKEN`：自動提供，用於開 Issue
- `PRODUCTHUNT_TOKEN`：Product Hunt GraphQL API Token。可在 Product Hunt 開發者頁面建立 App，將 client token 填入。GitHub Actions 執行時會自動注入給 collector。

### Product Hunt Token 設定流程

1. 前往 [Product Hunt API](https://www.producthunt.com/v2/api) 建立 Application，取得 `token`。
2. 在本機開發時，以環境變數輸入：
   ```bash
   set PRODUCTHUNT_TOKEN=<your-token>  # Windows PowerShell 請改用 $env:PRODUCTHUNT_TOKEN = "token"
   ```
3. 在 GitHub Repository 設定 `PRODUCTHUNT_TOKEN` Secret，供 GitHub Actions 使用。
4. 更新 `ops/feeds.yml` 將 `producthunt_daily` 的 `enabled` 改為 `true`，即可開始抓取。

### 測試覆蓋率（未來）

執行測試（需先建立 `tests/`）：
```bash
# 跑核心單元測試並顯示缺漏行（term-missing）
pytest tests/test_digest.py tests/test_collector.py --cov=ops --cov-report=term-missing

# 產生完整 HTML 覆蓋率報告（Windows 可用 start 開啟）
pytest tests/ --cov=ops --cov-report=html && start htmlcov/index.html
```

目前測試涵蓋：
- `digest.py`：`load_entries()`、`generate_markdown()`、`parse_args()`、`setup_logging()` 與 `main()`（含 dry-run、例外流程），同時驗證空資料、格式錯誤 JSON、Markdown 產物與 logging side effect，確保失敗時能回傳正確錯誤碼。
- `collector.py`：`merge_entries()`、`build_payload()`、`fetch_rss_or_atom()`、`fetch_producthunt()`、`fetch_source()`；以 mock HTTP 驗證 200/4xx/5xx、timeout、重試與 token 缺失等情境，並確保寫檔與去重流程不會產生重複 entry。

> 若新增來源、I/O 行為或整合其他 API，請同步補測並維持覆蓋率 ≥ 80%；CI 建議在 pytest 命令加入 `--cov-fail-under=80`，並於開發階段審閱 `htmlcov/index.html` 以快速鎖定缺漏行數。`tests` workflow（[.github/workflows/tests.yml](.github/workflows/tests.yml)）已在 push 與 Pull Request 階段自動執行上述檢查並上傳 coverage artifact，請確保本機結果與 CI 一致。

#### 測試覆蓋率強化規畫
- **Collector 核心流程**：針對 `setup_logging()`、`write_payload()`、`parse_args()` 與 `main()` 的正常/異常路徑新增測試，用 `monkeypatch` 模擬 CLI 參數、設定載入、HTTP 抓取與寫檔錯誤（對應 `SystemExit` 1/2/3），確保實際執行腳本時可涵蓋所有判斷分支。
- **網路模組情境**：既有的 `fetch_rss_or_atom()`、`fetch_producthunt()` 測試會模擬成功、timeout、token 缺失與 GraphQL 失敗流程，後續如新增 source type，需覆用同樣的 mock pattern（含 retry 與日誌訊息）避免 coverage 回落。
- **覆蓋率守門機制**：CI 透過 `pytest ... --cov-fail-under=80` 阻擋低於門檻的 PR，同時將 `coverage.xml` 與 `htmlcov/` 打包成 artifact 供 Reviewer 下載檢視；建議開發者本機亦執行同一命令並檢查 HTML 報告的紅色段落後再提交。
- **未來增補項目**：若要進一步提升至 95% 以上，可考慮以 `importlib.reload` 模擬缺少 `feedparser`/`requests` 的 ImportError 分支，以及補齊 `PRODUCTHUNT_TOKEN` 設定錯誤與 logging handler 初始化失敗等極端情境。

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
