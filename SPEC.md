# 專案技術規格（SPEC）

## 1. 核心功能
- **多來源收集**：支援 RSS、REST API、GraphQL 與手動輸入，以 YAML 描述頻率與權重。
- **資料清理與標準化**：透過 `transform` 規格指派清理函式，確保輸出欄位一致。
- **AI 協助摘要**：可串接 OpenAI 函式呼叫產出標題、風險與建議行動，供人工覆核。
- **自動發布**：Workflow 會將結果輸出至 GitHub Issue，並預留 Hook 連結 Slack/Email。

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

## 5. 延伸規劃
- 建立 `tests/` 驗證 YAML schema 與輸出格式。
- 新增 `cache/` 以儲存 API 回應，搭配 TTL 減少外部呼叫。
- 支援 Webhook 通知與多語系摘要，增強跨區域協作。
