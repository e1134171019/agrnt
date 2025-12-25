# 專案技術規格（SPEC）

## 1. 核心功能
- **多來源收集**：支援 RSS/Atom feeds，以 YAML 描述來源、分類、標籤與啟用狀態。
- **資料清理與標準化**：自動去重（依 link）、截斷摘要（200 字）、統一時間格式。
- **Markdown 輸出**：產生結構化摘要，依 `category` → 來源分組，包含標題、連結、發布時間、標籤。
- **自動發布**：Workflow 每日自動開 GitHub Issue，並預留 Hook 連結 Slack/Email。

## 2. 技術棧
- **語言**：Python 3.10+（主要腳本）、Node.js 18+（未來可擴充即時處理服務）。
- **函式庫**：PyYAML、Requests、Rich（終端輸出強化，可選）。
- **自動化**：GitHub Actions、peter-evans/create-issue-from-file、cron schedule。
- **資料格式**：YAML/JSON 作為設定與輸出交換格式，Markdown 作為 Digest 主體。

## 3. 系統流程
1. Workflow 依排程或手動觸發。
2. `ops/collector.py` 讀取 `ops/feeds.yml`，抓取所有啟用來源並輸出 `out/raw-YYYY-MM-DD.json`。
3. `ops/digest.py` 讀取 JSON，產出 Markdown 草稿並寫入暫存檔與 GitHub Issue。
4. Intel Editor 進行二次編輯，完成後由 Insight Verifier 核對，必要時建立 `02-dev-task` 追蹤後續工作。

## 4. 成功驗收
- Collector：必須支援 `python ops/collector.py --dry-run`，離線也能確認設定。
- Digest：必須支援 `python ops/digest.py --dry-run`，完全依賴 JSON 不觸網。
- YAML schema 驗證通過，缺漏欄位須回傳非零代碼並紀錄 error。
- Issue 內容至少含日期、來源列表、建議行動區塊。

## 5. collector.py 詳細規格

### 輸入
- **設定檔位置**：`ops/feeds.yml`
- **YAML Schema**：
   ```yaml
   sources:
      - key: string              # 必填，唯一識別碼
         name: string             # 必填，來源名稱
         url: string              # 必填，RSS/Atom URL，Product Hunt 可填預設 API URL
         type: "rss" | "atom" | "producthunt"
         category: string         # 必填，Digest 的顯示分類（如 community/news/product）
         tags: array<string>      # 選填，標籤列表
         limit: int               # 選填，單一來源最大筆數（預設 50，Product Hunt 預設 20）
         enabled: boolean         # 選填，預設 true
   ```
   - `type=producthunt` 需搭配 `PRODUCTHUNT_TOKEN` 環境變數（GitHub Actions 使用 Secrets），利用 GraphQL API 抓取每日熱門貼文與 topics。

### 處理流程
1. **載入設定**：讀取 `ops/feeds.yml` 並驗證 schema（含 key 唯一性）。
2. **過濾來源**：僅處理 `enabled=true` 的來源。
3. **抓取資料**：
   - 使用 `requests.get(url, timeout=30)`
   - 使用 `feedparser.parse()` 解析 RSS/Atom
   - 每個來源最多取 50 筆 entries
    - `type=producthunt` 時改用 `requests.post(PRODUCTHUNT_API_URL)`，攜帶 Bearer token 及 GraphQL 查詢
4. **資料提取**：提取 title/link/summary/published，補上 `source_key`、`tags`。
5. **去重合併**：依 link 去重。
6. **產生 JSON**：
   - 輸出物件 `{ "meta": {...}, "entries": [...] }`
   - `meta` 至少包含 `generated_at`、`raw_entries`、`unique_entries`、`dedup_rate`、`category_counts`、`failed_sources`
   - `entries` 每筆包含 `source_key`、`source`、`category`、`title`、`url`、`summary_raw`、`published_at`、`fetched_at`、`tags`
   - `fetched_at` 使用 UTC ISO8601。

### 輸出
- **檔案**：`out/raw-YYYY-MM-DD.json`
- **日誌**：`logs/collector-YYYY-MM-DD.log`（僅非 `--dry-run` 模式會建立檔案，dry-run 仍有 console log）

### 失敗處理
- **網路錯誤**：自動重試 3 次，間隔 2 秒，失敗後記錄 WARNING 並跳過該來源（Product Hunt 亦適用）。
- **錯誤碼對照**：
   | Code | 說明 |
   | --- | --- |
   | 1 | 設定檔不存在、YAML 解析錯誤或缺少必要欄位 |
   | 2 | 沒有啟用來源或所有來源都抓取失敗 |
   | 3 | 寫入 JSON 檔案失敗 |
- **額外情境**：若缺少 `PRODUCTHUNT_TOKEN`，僅跳過該來源並記錄 ERROR，不會中斷整體流程。

### 執行模式
- `python ops/collector.py`：依當日日期輸出 JSON。
- `--date YYYY-MM-DD`：指定輸出檔名。
- `--dry-run`：僅輸出統計資訊，不寫檔。
- `--output`：自訂輸出路徑。

## 6. digest.py 詳細規格

### 輸入
- **資料來源**：`out/raw-YYYY-MM-DD.json`（Collector 產出，或 `--input` 指定檔案）。
- **欄位要求**：`entries` 列表中的每筆 JSON 至少包含 `source_key`、`source`、`category`、`title`、`url`、`summary_raw`、`published_at`、`tags`，可選 `fetched_at` 供追蹤抓取時間；同時 `meta` 提供內容品質指標供 Digest 與報表使用。
   ```json
   {
      "meta": {
         "generated_at": "2025-12-25T02:00:00+00:00",
         "raw_entries": 52,
         "unique_entries": 40,
         "dedup_rate": 0.2308,
         "category_counts": {"community": 12, "news": 10},
         "failed_sources": []
      },
      "entries": [
         {
            "source_key": "producthunt_daily",
            "source": "Product Hunt Daily",
            "category": "product",
            "title": "Cool Tool",
            "url": "https://example.com",
            "summary_raw": "完整摘要內容",
            "published_at": "2025-12-25T00:00:00Z",
            "fetched_at": "2025-12-25T02:00:00+00:00",
            "tags": ["startup", "AI"]
         }
      ]
   }
   ```

### 處理流程
1. **載入 JSON**：檔案不存在或解碼失敗即退出（code=1）。
2. **驗證內容**：確保為 list 並含必要欄位。
3. **產生 Markdown**：
   - 首段輸出「摘要指標」，包含去重率、分類統計、來源健康度與失敗來源列表（若 `meta` 提供）
   - 先依 `category`，再依來源排序分組
   - `summary_raw` 截斷至 200 字後加上 `...`
   - 顯示 `published_at`、來源、標籤
   - 於文末加入生成時間戳記

### 輸出
- **檔案**：`out/digest-YYYY-MM-DD.md`（若 `--output` 指定則寫入自訂路徑）。
- **日誌**：`logs/digest-YYYY-MM-DD.log`（無論 dry-run 與否皆生成）。
- **Dry-run**：Markdown 僅輸出至 stdout，方便預覽；仍會在 log 中記錄。

### 失敗處理
- **錯誤碼對照**：
   | Code | 說明 |
   | --- | --- |
   | 1 | JSON 檔案不存在、解析失敗、不是列表或缺欄位 |
   | 2 | JSON 為空（無任何 entries） |
   | 3 | Markdown 寫檔失敗 |
- **異常輸出**：所有錯誤皆透過 LOGGER 記錄並輸出到 stderr，方便 GitHub Actions 收斂到 Problems。

### 執行模式
- `python ops/digest.py`：讀取預設 JSON 並輸出 Markdown。
- `--input` / `--output`：覆寫預設檔案。
- `--date`：改用 `raw-{date}.json` 和 `digest-{date}.md`。
- `--dry-run`、`--verbose`：相同語意。

## 7. 延伸規劃
- 建立 `tests/` 驗證 YAML schema 與輸出格式。
- 新增 `cache/` 以儲存 API 回應，搭配 TTL 減少外部呼叫。
- 支援 Webhook 通知與多語系摘要，增強跨區域協作。
- 並行抓取來源（使用 asyncio 或 ThreadPoolExecutor）提升效能。
