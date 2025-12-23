# AI Agents 規範

## 專案概述
本專案是一個自動化資訊收集與摘要系統，使用 AI Agent 定期從多個來源抓取技術資訊並產生報告。

## Agent 角色定義

### 1. Content Collector Agent
**職責**：
- 從 `ops/feeds.yml` 定義的來源抓取最新資訊
- 過濾低質量或重複內容
- 將資料標準化後存入暫存區
- 確保每筆 entry 包含 `source_key`、`source`、`title`、`url`、`summary_raw`、`published_at`、`fetched_at`、`tags`

**執行時機**：每日凌晨 2:00 (UTC+8，GitHub Actions 觸發)

**輸出格式**：`out/raw-YYYY-MM-DD.json`，僅 JSON（無 Markdown）。

**工具腳本**：`python ops/collector.py [--date YYYY-MM-DD] [--dry-run]`

**輸出位置**：`out/raw-YYYY-MM-DD.json`

### 2. Digest Generator Agent
**職責**：
- 讀取 Content Collector 的 JSON 輸出
- 使用 AI 模型產生繁體中文摘要
- 自動建立 GitHub Issue 發布摘要

**執行時機**：Content Collector 完成後觸發

**輸出位置**：
- Markdown 檔案：`out/digest-YYYY-MM-DD.md`
- GitHub Issues（使用 `01-intel-digest.yml` 模板）
- **工具腳本**：`python ops/digest.py [--input out/raw-YYYY-MM-DD.json]`

## 程式碼規範

### Python
- 使用 **Black** 格式化，行寬 **88 字元**
- 所有函式必須有 **type hints**
- 錯誤處理必須記錄到 `logs/digest-YYYY-MM-DD.log`
- 使用 `pathlib.Path` 處理檔案路徑
- 外部請求必須設定 **timeout=30 秒**

### YAML
- 使用 **2 空格**縮排
- 所有設定檔必須包含註解說明用途
- 必要欄位：`name`、`url`、`type`

## 安全規則

### 禁止事項
- ❌ **絕對不要**將 API keys 寫入程式碼
- ❌ **絕對不要**提交 `.env` 檔案到版本控制
- ❌ **絕對不要**在 logs 中記錄敏感資訊

### 強制要求
- ✅ 所有密鑰使用 **GitHub Secrets** 管理
- ✅ 外部請求必須設定 **timeout**（預設 30 秒）
- ✅ 所有設定檔使用相對路徑

## Commit 與 PR 規範

### Commit Message 格式（Conventional Commits）
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type 類型**：
- `feat`: 新功能
- `fix`: 修復 bug
- `docs`: 文件更新
- `style`: 程式碼格式（不影響功能）
- `refactor`: 重構
- `test`: 測試
- `chore`: 雜項（建置、工具）

**範例**：
```
feat(digest): 新增 RSS feed 解析功能

- 支援 Atom 1.0 格式
- 自動偵測 encoding
- 新增錯誤重試機制

Closes #12
```

### Pull Request 規範
1. 必須填寫 **PR Template** 所有欄位
2. 必須關聯對應的 **Issue**（使用 `Closes #123`）
3. 必須通過所有 **CI 檢查**
4. 必須有至少 **1 位 reviewer** 批准
5. 程式碼變更必須包含對應的**測試**

## 任務交付標準（Definition of Done, DoD）

### 開發任務
- [ ] 程式碼符合規範（Black、type hints）
- [ ] 已撰寫單元測試（覆蓋率 > 80%）
- [ ] 已更新相關文件
- [ ] 本地測試通過
- [ ] PR 已被 review 並合併
- [ ] logs/ 無錯誤訊息

### Intel Digest 任務
- [ ] `ops/collector.py` 成功執行並輸出 `out/raw-YYYY-MM-DD.json`
- [ ] `ops/digest.py` 成功執行
- [ ] 產生 `out/digest-YYYY-MM-DD.md`
- [ ] Markdown 格式正確
- [ ] 來源標註完整
- [ ] 已建立對應 GitHub Issue
- [ ] Issue 使用正確模板

## 工作流程

### 1. 新增資料來源
```bash
# 1. 編輯 feeds.yml
code ops/feeds.yml

# 2. 測試抓取
python ops/collector.py --dry-run
python ops/digest.py --dry-run

# 3. 提交 PR
git checkout -b feat/add-new-feed
git add ops/feeds.yml
git commit -m "feat(feeds): 新增 TechCrunch RSS 來源"
git push origin feat/add-new-feed
```

使用 **02-dev-task.yml** Issue 模板追蹤

### 2. 修改 Agent 行為
1. 更新 `AGENTS.md` 或 `SPEC.md`
2. 通知團隊進行 **code review**
3. 合併後自動套用到所有 Agent

### 3. 每日執行檢查
```bash
# 檢查最新 logs
cat logs/digest-$(date +%Y-%m-%d).log

# 檢查輸出檔案
ls -lh out/digest-*.md
```

## 注意事項
- 所有回應和文件使用**繁體中文**
- Commit message 使用 **Conventional Commits** 格式
- 每次執行完成後檢查 `logs/` 確認無錯誤
- 定期清理舊的 `out/` 和 `logs/` 檔案（保留最近 30 天）
