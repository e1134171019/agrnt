# 自動化情資管線專案

本專案是一套用於自動收集與整理資訊的工作流程，整合多種資料來源、排程機制與 AI 輔助摘要，協助團隊快速獲得每日情資與行動建議。

## 功能亮點
- **資料收集**：透過 `ops/feeds.yml` 定義 RSS、API、GraphQL 等來源，並可指定更新頻率。
- **摘要產生**：`ops/digest.py` 依排程輸出 Markdown 草稿，供 Intel Editor 加工。
- **自動化排程**：`.github/workflows/daily-intel-issue.yml` 會在設定時間建立 Digest Issue。
- **角色協作**：`AGENTS.md` 描述多位 AI/人力代理如何協同維運。

## 快速開始
1. 安裝 Python 3.10+ 並執行 `pip install -r requirements.txt`（可依實際需求建立）。
2. 依照 `SPEC.md` 補齊資料來源與技術設定。
3. 執行 `python ops/digest.py --dry-run` 以檢查輸出格式。
4. 設定 GitHub Secrets（如 `INTEL_BOT_TOKEN`），啟用每日排程。

## 目錄導覽
- `AGENTS.md`：AI Agent 與人員角色說明。
- `SPEC.md`：功能列表、技術棧與驗證準則。
- `ops/`：資料來源設定與摘要腳本。
- `.github/`：Issue/PR 模板及排程 workflow。
