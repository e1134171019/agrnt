import os
import json
import logging
import subprocess
import time
import requests
from pathlib import Path
from google import genai
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import markdown
from playwright.sync_api import sync_playwright

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent
OUT_DIR = PROJECT_ROOT / "out"
DOCS_DIR = PROJECT_ROOT / "docs"
ARSENAL_PATH = PROJECT_ROOT / "Brownfield_Verified_Arsenal.md"
ARSENAL_PDF_PATH = PROJECT_ROOT / "Brownfield_Verified_Arsenal.pdf"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
LOGGER = logging.getLogger(__name__)

RESEARCH_DOCS = {
    "研究規劃說明書（P1-P4 × 130個問題 × 技術選型 × RBv3架構 × 優先缺口）": PROJECT_ROOT / "我的規劃.md",
}

def load_research_context() -> str:
    """載入研究文件內容"""
    context_parts = []
    for doc_name, path in RESEARCH_DOCS.items():
        if path.exists():
            content = path.read_text(encoding='utf-8')
            context_parts.append(f"### {doc_name}\n\n{content}")
        else:
            LOGGER.warning(f"找不到研究文件: {path}")

    if not context_parts:
        LOGGER.error("沒有找到任何研究文件！")
        return ""
    
    return "\n\n---\n\n".join(context_parts)

def fetch_raw_intel_entries() -> list:
    """從 out 目錄讀取收集器抓下來的原始情報 JSON"""
    LOGGER.info("正在從本地抓取原始情報 (生肉貼文)...")
    entries = []
    try:
        if OUT_DIR.exists():
            # 找到最新的 raw json 或讀取全部
            for json_file in OUT_DIR.glob("raw-*.json"):
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    entries.extend(data.get("entries", []))
        LOGGER.info(f"成功抓取 {len(entries)} 篇原始生肉情報。")
        return entries
    except Exception as exc:
        LOGGER.error(f"讀取本地原始情報失敗: {exc}")
        return []

@retry(wait=wait_exponential(multiplier=15, min=30, max=120), stop=stop_after_attempt(5))
def generate_content_with_retry(client, prompt: str) -> str:
    """封裝 Gemini API 呼叫並加入重試機制，專門應對 429 限制"""
    return client.models.generate_content(model='gemini-2.5-flash', contents=prompt).text

def ask_ollama(prompt: str, model="qwen2.5:14b") -> str:
    """呼叫本機 Ollama API"""
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_ctx": 16384  # 放寬 Context Window，以防 15 篇原始貼文過長
        }
    }
    try:
        # 長時間等待推論，5070 Ti 跑 14B 大約需幾秒到幾十秒
        response = requests.post(url, json=payload, timeout=240)
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        LOGGER.error(f"本機 Ollama API 呼叫失敗: {e}")
        return ""

def generate_content_hybrid(client, prompt: str, role_name: str) -> str:
    """混合架構：嘗試 Ollama 主力，失敗或產出過短 (判斷為品質不佳) 時 Fallback 至 Gemini"""
    LOGGER.info(f"[{role_name}] 嘗試優先調用本機 Ollama 引擎 (qwen2.5:14b)...")
    ollama_txt = ask_ollama(prompt)
    
    # 判斷 Fallback 條件：如果報錯為空字串，或者產出過度簡短(少於 50 字) 視為解釋不好
    if not ollama_txt or len(ollama_txt) < 50:
        LOGGER.warning(f"[{role_name}] ⚠️ 本機模型產出異常或品質過低 (字數: {len(ollama_txt)})，啟動 Gemini API 備援支援！")
        gemini_txt = generate_content_with_retry(client, prompt)
        return gemini_txt
    return ollama_txt

def run_multi_agent_review(batch_idx: int, batch_text: str, research_context: str, client: genai.Client) -> str:
    LOGGER.info(f"== 開始會審 Batch {batch_idx} == (Hybrid 架構：Ollama 主力 / Gemini 備援)")
    
    # 1. 戰略軍師 Prompt (萃取 Top 50)
    strategist_prompt = f"""你是一位工業 5.0 × 中小企業製造 AI 的頂級首席技術長兼戰略幕僚。
你的任務是：閱讀「核心研究文件」，並從我提供的「歷史情報總匯 (包含多篇大雜燴的新聞摘要)」中，
挖掘出最精華、最能填補我們研究缺口的 50 篇重點科技或論文。

=== 研究核心文件 ===
{research_context}

=== 本批次歷史情報 ===
{batch_text}

請嚴格輸出以下格式的 Top 50 戰略提案：
### 📍 TOP 1: [文章標題或工具名稱]
- **內容摘要：** 簡要描述這是什麼技術
- **命中缺口：** 對應研究中的哪個問題編號（如 E01、P1...）
- **初步戰略提案：** 這項新技術有何特點？建議在我們的研究中如何應用？

### 📍 TOP 2... (以此類推，直到挑滿 50 篇)
"""
    try:
        LOGGER.info(f"Batch {batch_idx} - 軍師正在篩選精華...")
        initial_insight = generate_content_hybrid(client, strategist_prompt, "戰略軍師")
        time.sleep(1) # 稍微緩衝
        
        # 2. 廠長魔鬼審查 Prompt
        critic_prompt = f"""你是一位深諳工廠實務的廠長兼工業 5.0 架構師（魔鬼審查員）。
請嚴格檢視 AI 戰略軍師提出的「Top 50 戰略提案」。你的審查核心不再是單純的硬體算力規格，而是基於我們《中小企業板金製造現場智慧化系統 研究說明書》定義的根本環境與痛點，並且以實務軟體工程師的角度戳破學術界的幻想。

=== 我們的核心研究計畫 (Brownfield 升級藍圖) ===
{research_context}

你的考核基準（戰略與實務交火）：
1. 開源可用性與落地度 (大屠殺條件，最重要)：請嚴厲質疑這篇文章提到的技術【到底有沒有釋出實際的開源套件 (GitHub/HuggingFace)】？還是只是微軟/Google/大學實驗室發表的「紙上談兵」、「只聞樓梯響的發表會模型」？如果沒有實用程式碼資源、不給權重，完全無法在我們工廠 clone 下來使用，一律直接 REJECT！
2. Brownfield 物理與環境抗性：提案是否忽略了我們工廠的致命環境條件？例如：金屬嚴重反光 (B08)、冷啟動根本沒有大量標註資料可訓練 (B06)、老機台不准改動安全迴路與設備 (B01/B02)？
3. 實務生產節奏衝擊：系統要求是否會打亂師傅的步調 (B05)？端到端延遲是否會嚴重拖慢製程 (B12，即使我們後台有 RTX 5070 Ti 可以卸載運算，但廠內網路不穩 B03 仍是一大挑戰)？系統犯錯時會不會亂攔截導致師傅暴怒不用 (B13)？
4. 與目前架構的相容性：該提案是否與我們設計的「事件化證據鏈 (RBv3)」、「多代理人 (Agentic AI)」的戰略重點相容？

以下是軍師提出的 Top 50 歷史精華戰略：
{initial_insight}

請逐篇評估，格式如下：
### 審查 TOP X: [文章標題]
- **【判定結果】**: PASS 或 REJECT
- **【廠長嚴批】**: (詳細說明理由，請強迫自己結合上述的 Brownfield 痛點編號 B01~B15 或是開源性進行駁火攻擊)
"""
        LOGGER.info(f"Batch {batch_idx} - 廠長正在進行魔鬼極限審查...")
        critic_feedback = generate_content_hybrid(client, critic_prompt, "機車廠長")
        time.sleep(1) # 稍微緩衝
        
        # 3. 戰略軍師自我修正 (Reflection)
        if "REJECT" in critic_feedback.upper():
            LOGGER.info(f"Batch {batch_idx} - 有提案被退回，軍師正在重新修正降級版...")
            revise_prompt = f"""軍師，你剛剛從歷史情報中挖出的 Top 50 提案被實務廠長逐篇無情批評了。
以下是廠長的審查意見：
{critic_feedback}

=== 原初稿內容 ===
{initial_insight}

請執行自我修正 (Self-Correction)。重新寫一份「歷史精華情報認證版」。
對於被 `REJECT` 的提案，你必須改為「降級妥協方案」（例如大模型改小模型、雲端離線處理、改為記錄不做即時等），或直接標註「因硬體限制擱置」。
對於被 `PASS` 的提案，請保留並寫入廠長的警語。

輸出格式：
### 🎖️ [文章標題]
- **原始技術發現：** ...
- **最終可落地方案 (經廠長審查)：** (結合你的原意與廠長的限制，給出最務實的做法，並標註可部署在哪個節點)
"""
            final_insight = generate_content_hybrid(client, revise_prompt, "戰略軍師(修正版)")
            time.sleep(1) # 稍微緩衝
        else:
            final_insight = initial_insight + f"\n\n*(全數通過廠長審查)*\n{critic_feedback}"
            
        return final_insight

    except Exception as exc:
        LOGGER.error(f"Batch {batch_idx} 多次嘗試呼叫 Gemini API 仍舊失敗，略過此批次: {exc}")
        return ""

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        LOGGER.error("未找到 GEMINI_API_KEY 環境變數，請先設定 $env:GEMINI_API_KEY")
        return

    research_context = load_research_context()
    if not research_context:
        return

    issues = fetch_raw_intel_entries()
    if not issues:
        LOGGER.info("無可用原始情報進行大會審。")
        return
        
    # --- 依指揮官指示：將範圍放到前 500 篇生肉 ---
    LOGGER.info("⚠️ 偵測到指示：直接吞吐 500 篇原始生肉貼文。")
    issues = issues[:500]

    client = genai.Client(api_key=api_key)
    
    # Batch Processing: 將切分為每 15 篇一綑 (Batch)
    batch_size = 15
    all_distilled_insights = []
    
    for i in range(0, len(issues), batch_size):
        batch_issues = issues[i:i + batch_size]
        batch_idx = (i // batch_size) + 1
        
        # 合併此批次的文本
        batch_text_parts = []
        for iss in batch_issues:
            title = iss.get('title', '無標題')
            body = iss.get('summary_raw', '')
            url = iss.get('url', '')
            source = iss.get('source', '')
            batch_text_parts.append(f"## {title}\n來源: {source} ({url})\n{body[:2500]}") # 放寬到 2500 字，確保完整性
        
        batch_text_combined = "\n\n".join(batch_text_parts)
        
        # 執行雙重 Agent 審查
        insight = run_multi_agent_review(batch_idx, batch_text_combined, research_context, client)
        if insight:
            all_distilled_insights.append(insight)

    # 彙整與輸出
    LOGGER.info("所有批次審閱完成，正在匯集成武庫大全...")
    final_md = "# 🏭 Brownfield 老工廠落地認證兵器譜 (歷史文獻蒸餾)\n\n"
    final_md += "> 本檔案由戰略軍師與魔鬼廠長 (Jetson 8GB / 2s 延遲) 對過去百篇情報進行雙重審核並過濾後，最終殘存的「絕對可落地」兵器裝備庫。\n\n"
    
    for idx, insight in enumerate(all_distilled_insights, 1):
        final_md += f"## 📦 批次探勘成果 {idx}\n\n" + insight + "\n\n---\n\n"

    try:
        with open(ARSENAL_PATH, 'w', encoding='utf-8') as f:
            f.write(final_md)
        LOGGER.info(f"Markdown 寫入完成: {ARSENAL_PATH}")
        
        # 轉換為 PDF
        LOGGER.info("正在使用 Playwright 將結果渲染成 PDF...")
        html_content = markdown.markdown(final_md, extensions=['tables', 'fenced_code'])
        
        styled_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: "Microsoft JhengHei", "PingFang TC", "Helvetica Neue", Helvetica, Arial, sans-serif;
                line-height: 1.6;
                padding: 40px;
                color: #2c3e50;
            }}
            h1 {{ color: #1a252f; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            h2 {{ color: #e74c3c; margin-top: 30px; }}
            h3 {{ color: #2980b9; }}
            code {{ background-color: #f8f9fa; padding: 2px 5px; border-radius: 4px; font-family: monospace; }}
            pre {{ background-color: #f8f9fa; padding: 15px; border-radius: 4px; overflow-x: auto; border: 1px solid #ddd; }}
            blockquote {{ border-left: 4px solid #3498db; margin-left: 0; padding-left: 15px; color: #555; background-color: #f4f6f7; padding: 10px 15px; }}
            li {{ margin-bottom: 8px; }}
        </style>
        </head>
        <body>
        {html_content}
        </body>
        </html>
        """
        
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_content(styled_html)
            page.pdf(path=str(ARSENAL_PDF_PATH), format="A4", margin={"top": "20px", "right": "20px", "bottom": "20px", "left": "20px"})
            browser.close()
            
        LOGGER.info(f"大成功！歷史煉丹完成，純金已鍛造成 PDF 手冊: {ARSENAL_PDF_PATH}")
    except Exception as e:
        LOGGER.error(f"寫入或生成 PDF 檔案失敗: {e}")

if __name__ == "__main__":
    main()
