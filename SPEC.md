# 專案技術規格（SPEC）

## 1. 核心功能
- **多來源收集**：支援 RSS/Atom feeds，以 YAML 描述來源、標籤與啟用狀態。
- **資料清理與標準化**：自動去重（依 link）、截斷摘要（200 字）、統一時間格式。
- **Markdown 輸出**：產生結構化摘要，依來源分組，包含標題、連結、發布時間、標籤。
- **自動發布**：Workflow 每日自動開 GitHub Issue，並預留 Hook 連結 Slack/Email。

## 2. 技術棧
- **語言**：Python 3.10+（主要腳本）、Node.js 18+（未來可擴充即時處理服務）。
- **函式庫**：PyYAML、Requests、Rich（終端輸出強化，可選）。
- **自動化**：GitHub Actions、peter-evans/create-issue-from-file、cron schedule。
- **資料格式**：YAML/JSON 作為設定與輸出交換格式，Markdown 作為 Digest 主體。

## 3. 系統流程
1. Workflow 依排程或手動觸發。
2. `ops/digest.py` 讀取 `ops/feeds.yml`，拉取資料或使用 mock，並產出 Markdown 草稿。
3. 草稿寫入暫存檔與 GitHub Issue，Intel Editor 進行二次編輯。
4. 完成後由 Insight Verifier 核對，必要時建立 `02-dev-task` 追蹤後續工作。

## 4. 成功驗收
- 支援 `python ops/digest.py --dry-run`（離線亦可執行）。
- YAML schema 驗證通過，缺漏欄位須回傳非零代碼並紀錄 error。
- Issue 內容至少含日期、來源列表、建議行動區塊。

## 5. digest.py 詳細規格

### 輸入
- **設定檔位置**：`ops/feeds.yml`
- **YAML Schema**：
  ```yaml
  sources:
    - name: string         # 必填，來源名稱
      url: string          # 必填，RSS/Atom feed URL
      type: "rss" | "atom" # 必填，feed 類型
      tags: array<string>  # 選填，標籤列表
      enabled: boolean     # 選填，預設 true
  ```

### 處理流程
1. **載入設定**：讀取 `ops/feeds.yml` 並驗證 schema
2. **過濾來源**：僅處理 `enabled=true` 的來源
3. **抓取資料**：
   - 使用 `requests.get(url, timeout=30)`
   - 使用 `feedparser.parse()` 解析 RSS/Atom
   - 每個來源最多取 50 筆 entries
4. **資料提取**：提取 title, link, summary, published, tags
5. **去重合併**：依 link 去重，合併所有來源
6. **產生 Markdown**：
   - 依來源分組
   - 摘要截斷至 200 字
   - 加入時間戳記

### 輸出
- **檔案位置**：`out/digest-YYYY-MM-DD.md`（自動建立 out/ 目錄）
- **日誌位置**：`logs/digest-YYYY-MM-DD.log`（僅非 --dry-run 模式）
- **Markdown 格式**：
  ```markdown
  # 技術資訊摘要 - YYYY-MM-DD
  
  ## 來源名稱
  
  ### [文章標題](連結)
  發布於：時間戳記
  
  摘要內容（最多 200 字）...
  
  **來源**：來源名稱
  **標籤**：#tag1 #tag2
  
  ---
  
  *本摘要由自動化系統產生於 YYYY-MM-DD HH:MM*
  ```

### 失敗處理
- **網路錯誤**：自動重試 3 次，間隔 2 秒，失敗後記錄 WARNING 並跳過該來源
- **YAML 格式錯誤**：立即退出，exit code=1，錯誤訊息輸出到 stderr
- **設定檔缺少必要欄位**：exit code=1，明確指出缺少的欄位
- **所有來源失敗**：exit code=2，記錄到 logs/
- **檔案寫入失敗**：exit code=3，記錄錯誤訊息
- **部分來源失敗**：繼續執行，僅記錄 WARNING，成功來源仍會產生輸出

### 執行模式
- **標準模式**：`python ops/digest.py` - 產生今日摘要
- **指定日期**：`python ops/digest.py --date 2025-12-20`
- **預覽模式**：`python ops/digest.py --dry-run` - 不寫檔案，輸出到 stdout
- **詳細日誌**：`python ops/digest.py --verbose` - DEBUG 級別日誌
- **自訂輸出**：`python ops/digest.py --output custom.md`

## 6. 延伸規劃
- 建立 `tests/` 驗證 YAML schema 與輸出格式。
- 新增 `cache/` 以儲存 API 回應，搭配 TTL 減少外部呼叫。
- 支援 Webhook 通知與多語系摘要，增強跨區域協作。
- 並行抓取來源（使用 asyncio 或 ThreadPoolExecutor）提升效能。
