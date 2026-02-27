import os
import json
import logging
from pathlib import Path
from google import genai
import requests

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
OUT_DIR = PROJECT_ROOT / "out"
DOCS_DIR = PROJECT_ROOT / "docs"
LOGS_DIR = PROJECT_ROOT / "logs"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)

RESEARCH_DOCS = {
    "研究規劃說明書": PROJECT_ROOT / "我的規劃.md",
}

def load_research_context() -> str:
    """載入研究文件內容"""
    context_parts = []
    for doc_name, path in RESEARCH_DOCS.items():
        if path.exists():
            content = path.read_text(encoding='utf-8')
            context_parts.append(f"### {doc_name}\n\n{content}")
    return "\n\n---\n\n".join(context_parts)

def get_latest_raw_and_digest():
    """找出最新一天的 raw JSON 與對應的 digest MD"""
    if not OUT_DIR.exists():
        LOGGER.error("找不到 out/ 目錄。")
        return None, None
    
    # 找最新的 raw json
    raw_files = sorted(list(OUT_DIR.glob("raw-*.json")), key=os.path.getmtime, reverse=True)
    if not raw_files:
        LOGGER.error("找不到任何 raw-*.json 原始情報檔。")
        return None, None
        
    latest_raw = raw_files[0]
    
    # 從檔名解析日期，例如 raw-2026-02-26.json -> 2026-02-26
    date_str = latest_raw.stem.replace("raw-", "")
    digest_file = OUT_DIR / f"digest-{date_str}-main.md"
    
    if not digest_file.exists():
        LOGGER.warning(f"找到 {latest_raw.name} 但找不到對應的高階摘要 {digest_file.name}，將所有視為落網之魚！")
        return latest_raw, None
        
    return latest_raw, digest_file

def fetch_rejected_entries(raw_path, digest_path):
    """比對並抓出沒有進入 Digest 的文章"""
    try:
        with open(raw_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            all_entries = raw_data.get("entries", [])
    except Exception as e:
        LOGGER.error(f"讀取原始資料失敗: {e}")
        return []
        
    if not digest_path or not digest_path.exists():
        return all_entries
        
    try:
        with open(digest_path, "r", encoding="utf-8") as f:
            digest_content = f.read().lower()
    except Exception as e:
        LOGGER.error(f"讀取摘要資料失敗: {e}")
        return all_entries

    rejected_entries = []
    
    # 將 digest 內容清理成沒有特殊符號的檢索池
    import re
    cleaned_digest = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '', digest_content)
    
    for entry in all_entries:
        title = entry.get("title", "")
        if not title:
            continue
            
        # 移除特殊符號進行比對
        cleaned_title = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '', title.lower())
        
        # 只要標題不為空，且清空符號後沒有出現在摘要中
        if len(cleaned_title) > 5 and cleaned_title not in cleaned_digest:
            rejected_entries.append(entry)
            
    LOGGER.info(f"當日總情報數: {len(all_entries)} | 被選入摘要的情報約: {len(all_entries) - len(rejected_entries)} | 落榜情報: {len(rejected_entries)}")
    return rejected_entries

def ask_ollama(prompt: str, model="qwen2.5:14b", timeout=120) -> str:
    """呼叫本機 Ollama API"""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    try:
        response = requests.post(url, json=payload, timeout=timeout)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        LOGGER.error(f"本機 Ollama API 呼叫失敗: {e}")
        return ""

def audit_rejected_entries(rejected_entries, research_context):
    """讓軍師去稽核這些落選名單，找出漏報的真黃金"""
    if not rejected_entries:
        LOGGER.info("沒有落榜名單可以審查。")
        return

    # 為免一次吃不消，隨機挑選或前 30 篇來做沙盤推演
    sample_size = min(30, len(rejected_entries))
    sample_entries = rejected_entries[:sample_size]
    
    batch_text_parts = []
    for idx, iss in enumerate(sample_entries):
        title = iss.get('title', '無標題')
        body = iss.get('summary_raw', '')
        url = iss.get('url', '')
        batch_text_parts.append(f"### [遺珠檔案 {idx+1}]: {title}\n連結: {url}\n內文: {body[:1500]}") # 限制長度
    
    batch_text_combined = "\n\n".join(batch_text_parts)
    
    prompt = f"""你是一名「情報稽核官」。我們的前線篩選系統今天砍掉了幾百篇情報。
我現在從「被刪除的垃圾堆 (落榜文章)」中抽取了 {sample_size} 篇給你重新審視。

=== 我們的核心研究計畫 (Brownfield 升級藍圖) ===
{research_context}

=== 落榜文章樣本 ===
{batch_text_combined}

🚨 你的任務：
請帶著「挑骨頭」的心態，嚴格比對這 {sample_size} 篇文章與我們的《核心計畫》。
大部分的文章真的都是垃圾（與我們計畫無關），但你的工作是找出「誤殺」。

只要你發現其中有【任何一篇】是高度符合我們 B01~B15 痛點，或是能作為我們 AI 廠長武器的開源資源，請把它揪出來，並大聲譴責前線篩選器！
如果全部看完覺得前線刪得好，請回答「前線篩選準確，本次抽樣無漏網之魚」。

格式：
### 😡 嚴重漏殺發現：[文章標題]
- **理由**：(這篇文章到底多棒？為何符合我們的 Brownfield 計畫？前線系統把它當垃圾是不是瞎了眼？)
- **建議補救**：(我們應該立刻補進哪個模組裡？)
"""
    LOGGER.info(f"正在對 {sample_size} 篇落榜文章進行遺珠稽核推論 (等待 Ollama 回應)...")
    result = ask_ollama(prompt, timeout=240)
    
    print("\n" + "="*50)
    print("      🕵️‍♂️ 情報大稽核結果出爐 🕵️‍♂️")
    print("="*50 + "\n")
    if result:
        print(result)
    else:
        print("模型呼叫失敗或逾時。")
        
def main():
    research_context = load_research_context()
    if not research_context:
        return
        
    raw_path, digest_path = get_latest_raw_and_digest()
    if not raw_path:
        return
        
    LOGGER.info(f"基準比對源：\n- 原始生肉檔：{raw_path}\n- 摘要產出檔：{digest_path if digest_path else '無'}")
    
    rejected = fetch_rejected_entries(raw_path, digest_path)
    
    # 啟動稽核
    audit_rejected_entries(rejected, research_context)

if __name__ == "__main__":
    main()
