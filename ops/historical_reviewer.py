import os
import json
import logging
import subprocess
from pathlib import Path
from google import genai
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

def fetch_historical_issues() -> list:
    """使用 GitHub CLI 抓取過去 100 篇 issue 的內容"""
    LOGGER.info("正在從 GitHub 抓取過去 100 篇 Issue 內容...")
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--state", "all", "--limit", "100", "--json", "title,body"],
            capture_output=True,
            text=True,
            check=True
        )
        issues = json.loads(result.stdout)
        # 過濾出 [Digest - Main] 或是包含大量摘要的 issue
        intel_issues = [iss for iss in issues if "摘要" in iss.get("title", "") or "Digest" in iss.get("title", "")]
        LOGGER.info(f"成功抓取 {len(issues)} 篇 Issue，其中符合情報特徵的有 {len(intel_issues)} 篇。")
        return intel_issues
    except Exception as exc:
        LOGGER.error(f"抓取 GitHub Issues 失敗: {exc}")
        return []

def run_multi_agent_review(batch_idx: int, batch_text: str, research_context: str, client: genai.Client) -> str:
    LOGGER.info(f"== 開始會審 Batch {batch_idx} ==")
    
    # 1. 戰略軍師 Prompt (萃取 Top 5)
    strategist_prompt = f"""你是一位工業 5.0 × 中小企業製造 AI 的頂級首席技術長兼戰略幕僚。
你的任務是：閱讀「核心研究文件」，並從我提供的「歷史情報總匯 (包含多篇大雜燴的新聞摘要)」中，
挖掘出最精華、最能填補我們研究缺口的 5 篇重點科技或論文。

=== 研究核心文件 ===
{research_context}

=== 本批次歷史情報 ===
{batch_text}

請嚴格輸出以下格式的 Top 5 戰略提案：
### 📍 TOP 1: [文章標題或工具名稱]
- **內容摘要：** 簡要描述這是什麼技術
- **命中缺口：** 對應研究中的哪個問題編號（如 E01、P1...）
- **初步戰略提案：** 這項新技術有何特點？建議在我們的研究中如何應用？

### 📍 TOP 2... (以此類推)
"""
    try:
        LOGGER.info(f"Batch {batch_idx} - 軍師正在篩選精華...")
        resp1 = client.models.generate_content(model='gemini-2.5-flash', contents=strategist_prompt)
        initial_insight = resp1.text
        
        # 2. 廠長魔鬼審查 Prompt
        critic_prompt = f"""你是一位老派的工廠廠長兼工業 5.0 架構師（魔鬼審查員）。
無情檢視 AI 戰略軍師剛從歷史文獻中挖出來的「Top 5 戰略提案」，逐篇抓出它們無法在 Brownfield (老式折床工廠) 落地的缺點。

你的考核基準（極限條件 Checklist）：
1. 邊緣算力限制：系統只能跑在 Jetson Orin Nano 8GB 上。
2. 網路環境極限：工廠內部網路不穩，影響機台作動的推論必須離線。
3. 即時性要求：端到端延遲 (E2E Latency) 不能超過 2 秒。
4. 感測噪聲預期：金屬會反光、現場有油污粉塵。
5. 硬體改裝禁忌：不准改動機器原廠的安全迴路與硬體。

以下是軍師提出的 Top 5 歷史精華戰略：
{initial_insight}

請逐篇評估，格式如下：
### 審查 TOP X: [文章標題]
- **【判定結果】**: PASS 或 REJECT
- **【廠長嚴批】**: (詳細說明理由，若 REJECT 請點出違反哪條底線)
"""
        LOGGER.info(f"Batch {batch_idx} - 廠長正在進行魔鬼極限審查...")
        resp2 = client.models.generate_content(model='gemini-2.5-flash', contents=critic_prompt)
        critic_feedback = resp2.text
        
        # 3. 戰略軍師自我修正 (Reflection)
        if "REJECT" in critic_feedback.upper():
            LOGGER.info(f"Batch {batch_idx} - 有提案被退回，軍師正在重新修正降級版...")
            revise_prompt = f"""軍師，你剛剛從歷史情報中挖出的 Top 5 提案被實務廠長逐篇無情批評了。
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
            resp3 = client.models.generate_content(model='gemini-2.5-flash', contents=revise_prompt)
            final_insight = resp3.text
        else:
            final_insight = initial_insight + f"\n\n*(全數通過廠長審查)*\n{critic_feedback}"
            
        return final_insight

    except Exception as exc:
        LOGGER.error(f"Batch {batch_idx} 呼叫 Gemini API 失敗: {exc}")
        return ""

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        LOGGER.error("未找到 GEMINI_API_KEY 環境變數，請先設定 $env:GEMINI_API_KEY")
        return

    research_context = load_research_context()
    if not research_context:
        return

    issues = fetch_historical_issues()
    if not issues:
        LOGGER.info("無可用 Issue 進行歷史大會審。")
        return

    client = genai.Client(api_key=api_key)
    
    # Batch Processing: 將 Issue 切分為每 5 篇一綑 (Batch)
    batch_size = 5
    all_distilled_insights = []
    
    for i in range(0, len(issues), batch_size):
        batch_issues = issues[i:i + batch_size]
        batch_idx = (i // batch_size) + 1
        
        # 合併此批次的文本
        batch_text_parts = []
        for iss in batch_issues:
            title = iss.get('title', '無標題')
            body = iss.get('body', '')
            # 擷取部分摘要即可，避免單篇內文過長
            batch_text_parts.append(f"## {title}\n{body[:8000]}") # 取前 8000 字
        
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
