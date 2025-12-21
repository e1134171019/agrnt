# 測試覆蓋率報告

> 生成時間：2025-12-22  
> 測試框架：pytest 9.0.2  
> 覆蓋率工具：pytest-cov 7.0.0

---

## 📊 總體覆蓋率

| 檔案 | 語句數 | 已測試 | 覆蓋率 | 未覆蓋行 |
|------|--------|--------|--------|----------|
| **ops/digest.py** | 181 | 88 | **49%** | 93 行未覆蓋 |

### 未覆蓋的程式碼區段

#### 1. 匯入錯誤處理（第 20-31 行）
```python
except ImportError as exc:
    raise SystemExit("請先安裝 feedparser...")
```
- **原因**：測試環境已安裝所有依賴，無法觸發 ImportError
- **優先級**：低（生產環境必定安裝依賴）

#### 2. setup_logging() 函式（第 47-71 行）
```python
def setup_logging(verbose: bool = False, log_file: pathlib.Path | None = None) -> None:
    # ... 日誌設定邏輯
```
- **原因**：測試中未直接呼叫此函式
- **建議**：新增測試驗證日誌輸出格式

#### 3. fetch_feed() 函式（第 106-150 行）
```python
def fetch_feed(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    # ... 網路請求與 feedparser 邏輯
```
- **原因**：需要 mock HTTP 請求，較複雜
- **建議**：使用 `responses` 或 `unittest.mock` 模擬網路請求

#### 4. parse_args() 函式（第 215-238 行）
```python
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(...)
```
- **原因**：測試中未呼叫命令列解析
- **建議**：新增測試驗證參數解析邏輯

#### 5. main() 函式（第 243-295 行）
```python
def main() -> None:
    # ... 主程式邏輯
```
- **原因**：整合測試需要完整環境設定
- **建議**：新增整合測試或使用 `pytest.monkeypatch`

---

## ✅ 已測試功能（21 個測試案例）

### test_config.py（8 個測試）

| 測試名稱 | 測試目標 | 狀態 |
|----------|----------|------|
| `test_load_valid_config` | 載入有效設定檔 | ✅ PASSED |
| `test_load_config_file_not_found` | 檔案不存在處理 | ✅ PASSED |
| `test_load_config_invalid_yaml` | 無效 YAML 格式 | ✅ PASSED |
| `test_load_config_missing_sources` | 缺少 sources 欄位 | ✅ PASSED |
| `test_load_config_missing_required_fields` | 缺少必填欄位 | ✅ PASSED |
| `test_load_config_invalid_type` | type 欄位值不合法 | ✅ PASSED |
| `test_load_config_with_optional_fields` | 選填欄位處理 | ✅ PASSED |
| `test_load_config_empty_sources` | 空的 sources 列表 | ✅ PASSED |

**覆蓋率**：`load_config()` 函式 **100%**

---

### test_digest.py（13 個測試）

#### TestMergeEntries（6 個測試）

| 測試名稱 | 測試目標 | 狀態 |
|----------|----------|------|
| `test_merge_empty_lists` | 合併空列表 | ✅ PASSED |
| `test_merge_single_source` | 單一來源 | ✅ PASSED |
| `test_merge_multiple_sources` | 多個來源 | ✅ PASSED |
| `test_merge_removes_duplicates` | 去重功能（依 link） | ✅ PASSED |
| `test_merge_preserves_order` | 保留順序 | ✅ PASSED |
| `test_merge_empty_link_not_filtered` | 空 link 過濾 | ✅ PASSED |

**覆蓋率**：`merge_entries()` 函式 **100%**

---

#### TestGenerateMarkdown（7 個測試）

| 測試名稱 | 測試目標 | 狀態 |
|----------|----------|------|
| `test_generate_empty_entries` | 空 entries 列表 | ✅ PASSED |
| `test_generate_single_entry` | 單一 entry | ✅ PASSED |
| `test_generate_multiple_sources` | 多來源分組 | ✅ PASSED |
| `test_generate_truncates_long_summary` | 長摘要截斷 | ✅ PASSED |
| `test_generate_no_tags` | 無標籤處理 | ✅ PASSED |
| `test_generate_sorted_by_source` | 來源排序 | ✅ PASSED |
| `test_generate_includes_timestamp` | 時間戳記 | ✅ PASSED |

**覆蓋率**：`generate_markdown()` 函式 **100%**

---

## 📈 覆蓋率提升計畫

### 短期目標（達到 70%）

1. **新增 setup_logging() 測試**
   - 驗證 console handler 設定
   - 驗證 file handler 建立
   - 驗證日誌格式
   
   ```python
   def test_setup_logging_console(capsys):
       setup_logging(verbose=True)
       LOGGER.info("Test message")
       captured = capsys.readouterr()
       assert "Test message" in captured.out
   ```

2. **新增 parse_args() 測試**
   - 測試預設參數
   - 測試 --date, --output, --dry-run, --verbose
   
   ```python
   def test_parse_args_default():
       sys.argv = ["digest.py"]
       args = parse_args()
       assert args.date == dt.date.today().isoformat()
       assert args.dry_run is False
   ```

3. **新增 fetch_feed() mock 測試**
   - 使用 `responses` 模擬 HTTP 請求
   - 測試成功、Timeout、網路錯誤
   
   ```python
   @responses.activate
   def test_fetch_feed_success():
       responses.add(responses.GET, "https://example.com/feed.xml", body=RSS_CONTENT)
       entries = fetch_feed({"name": "Test", "url": "https://example.com/feed.xml"})
       assert len(entries) > 0
   ```

### 中期目標（達到 85%）

4. **新增 main() 整合測試**
   - 使用 `pytest.monkeypatch` 模擬 sys.argv
   - 使用 `tempfile` 建立臨時設定檔
   - 驗證完整流程

---

## 🎯 品質指標

| 指標 | 目標 | 現狀 | 狀態 |
|------|------|------|------|
| 測試覆蓋率 | 80% | 49% | ⚠️ 需改進 |
| 測試通過率 | 100% | 100% | ✅ 達標 |
| Type Hints | 100% | 100% | ✅ 達標 |
| 測試案例數 | 30+ | 21 | ⚠️ 需補充 |

---

## 🚀 執行測試

### 基本執行
```bash
pytest
```

### 產生覆蓋率報告
```bash
pytest --cov=ops --cov-report=term-missing
```

### 產生 HTML 報告
```bash
pytest --cov=ops --cov-report=html
# 開啟 htmlcov/index.html 查看
```

### 執行特定測試
```bash
pytest tests/test_config.py
pytest tests/test_digest.py::TestMergeEntries
pytest tests/test_digest.py::TestMergeEntries::test_merge_empty_lists
```

### 詳細輸出
```bash
pytest -v
pytest -vv  # 更詳細
```

---

## 📦 測試依賴

```txt
pytest>=9.0.0
pytest-cov>=7.0.0
black>=25.0.0
mypy>=1.19.0
```

安裝：
```bash
pip install -r requirements.txt
```

---

## 📝 測試標準

根據 `AGENTS.md` 規範：

- ✅ **測試覆蓋率**：目標 > 80%（現狀 49%，需改進）
- ✅ **Type Hints**：100% 覆蓋（已達標）
- ✅ **測試通過率**：100%（已達標）
- ✅ **DoD**：所有新功能必須包含測試

---

**下一步行動：**
1. ✅ 建立測試框架（已完成）
2. ✅ 撰寫核心函式測試（已完成）
3. ⏭️ 補充 setup_logging, parse_args 測試
4. ⏭️ 新增 fetch_feed mock 測試
5. ⏭️ 新增 main() 整合測試
6. ⏭️ 達到 80% 覆蓋率目標

**報告完成。** 🎉
