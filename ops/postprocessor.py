"""論文後處理模組：對 papers 類別進行 manufacturing applicability 評分。"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List

LOGGER = logging.getLogger("postprocessor")

# 研究問題對應關鍵字（對應 P1-P4 × 6M1E × 130 個問題 × 折床 × 板金 Brownfield）
# P1 狀態不可觀測：感知/重建/深度/點雲/三維
# P2 錯誤不可即時阻止：執行閘控/異常偵測/即時攔截
# P3 經驗不可複製：持續學習/少樣本/知識蒸餾/師傅
# P4 設計現場斷層：DXF/設計意圖/數位孿生/版本追蹤
# H 人維度：知識傳承/培訓/技能矩陣/人機互動
# M 機維度：老機台/PLC/感測器/預防保養/稼動率
# R 料維度：材料追溯/批號/材證/彈回量
# F 法維度：版本控制/SOP/NC程式/工程變更
# Q 測維度：量測/首件檢驗/品質追溯/OEE/Cpk
# E 環維度：金屬反光/光源/油膜/溫濕度
RESEARCH_KEYWORDS = [
    # P1 感知層
    "3d reconstruction", "depth", "point cloud", "rgb-d", "gaussian splatting",
    "pose estimation", "object detection", "scene understanding", "slam",
    "few-shot", "zero-shot", "imitation learning",
    # P2 執行層
    "anomaly detection", "execution", "gating", "interrupt",
    "fault detection", "quality control", "defect",
    # P3 知識層
    "continual learning", "incremental learning", "knowledge distillation",
    "rag", "retrieval", "expert", "knowledge base", "transfer learning",
    # P4 設計層
    "digital twin", "cad", "dxf", "design intent", "version control",
    "traceability", "sheet metal", "bending",
    # H 人維度：知識傳承與人機互動
    "knowledge transfer", "tacit knowledge", "apprentice", "skill assessment",
    "human-robot", "operator training", "worker assistance", "ar guidance",
    "augmented reality", "human-in-the-loop",
    # M 機維度：老機台與設備狀態
    "legacy equipment", "plc", "retrofit", "brownfield", "predictive maintenance",
    "machine monitoring", "opc-ua", "edge computing", "jetson",
    # R 料維度：材料追溯與特性
    "material traceability", "batch tracking", "material certificate",
    "springback", "material property", "alloy",
    # F 法維度：版本控制與製程標準
    "nc program", "sop", "ecn", "engineering change", "process planning",
    "cam", "nesting", "toolpath",
    # Q 測維度：品質量測與統計
    "first article inspection", "cpk", "oee", "measurement", "metrology",
    "statistical process control", "spc", "dimensional inspection",
    # E 環維度：環境感知
    "specular reflection", "lighting", "dust", "contamination",
]


def _score_heuristic(text: str) -> tuple[int, str]:
    """啟發式規則：依研究問題關鍵字命中數評分（P1-P4 + 6M1E）。"""
    hits = sum(1 for kw in RESEARCH_KEYWORDS if kw in text)
    score = min(100, 10 + hits * 12)

    notes: List[str] = []
    # P1 感知層
    if any(kw in text for kw in ["depth", "rgb-d", "point cloud", "3d reconstruction", "gaussian"]):
        notes.append("P1命中:感知/重建")
    # P2 執行層
    if any(kw in text for kw in ["anomaly", "fault", "defect", "gating"]):
        notes.append("P2命中:異常偵測/即時攔截")
    # P3 知識層
    if any(kw in text for kw in ["continual", "incremental", "rag", "retrieval", "few-shot", "distill"]):
        notes.append("P3命中:持續學習/知識")
    # P4 設計層
    if any(kw in text for kw in ["digital twin", "cad", "dxf", "traceability", "sheet metal", "bending"]):
        notes.append("P4命中:設計意圖/版本")
    # H 人維度
    if any(kw in text for kw in ["knowledge transfer", "tacit knowledge", "apprentice", "operator training", "ar guidance", "augmented reality"]):
        notes.append("H命中:知識傳承/人機互動")
    # M 機維度
    if any(kw in text for kw in ["legacy equipment", "plc", "retrofit", "brownfield", "predictive maintenance", "edge computing"]):
        notes.append("M命中:老機台/設備狀態")
    # R 料維度
    if any(kw in text for kw in ["material traceability", "batch tracking", "springback", "material property"]):
        notes.append("R命中:材料追溯/特性")
    # F 法維度
    if any(kw in text for kw in ["nc program", "sop", "ecn", "process planning", "cam", "nesting"]):
        notes.append("F命中:版本控制/製程")
    # Q 測維度
    if any(kw in text for kw in ["first article inspection", "cpk", "oee", "metrology", "spc"]):
        notes.append("Q命中:品質量測/統計")
    # E 環維度
    if any(kw in text for kw in ["specular reflection", "lighting", "dust", "contamination"]):
        notes.append("E命中:環境感知")
    note = "; ".join(notes) or "未命中P1-P4或6M1E核心問題"

    return score, note


def _score_with_llm(text: str) -> tuple[int | None, str]:
    """使用 OpenAI API（>=1.0）評分。"""
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not openai_key:
        return None, ""

    try:
        from openai import OpenAI

        client = OpenAI(api_key=openai_key)
        prompt = (
            f"你正在協助一個板金折床工廠的工業互聯網研究，研究有四個核心問題：\n"
            f"P1=現場狀態不可觀測（感知/重建/深度/點雲）\n"
            f"P2=錯誤不可即時阻止（異常偵測/執行閘控/即時攔截）\n"
            f"P3=師傅經驗不可複製（持續學習/少樣本/知識傳承/RAG）\n"
            f"P4=設計端與現場斷層（DXF意圖橋接/版本追蹤/追溯）\n\n"
            f"請基於以下論文標題與摘要，給出 0-100 的研究相關度分數，\n"
            f"並用一句話說明命中了哪個問題（P1/P2/P3/P4）以及原因（返回純文字）。\n\n{text}"
        )
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.0,
        )
        content = resp.choices[0].message.content.strip()
        m = re.search(r"(\d{1,3})", content)
        score = int(m.group(1)) if m else None
        return score, content
    except Exception:
        LOGGER.warning("LLM 評分失敗，回退到啟發式")
        return None, "(LLM 處理失敗，使用啟發式結果)"


def postprocess_paper(entry: Dict[str, Any]) -> None:
    """對單一 paper entry 加上 manufacturing 評分與 integration note。"""
    title = entry.get("title", "") or ""
    summary = entry.get("summary_raw", "") or ""
    text = f"{title}\n\n{summary}".lower()

    # 先嘗試 LLM，失敗則用啟發式
    score, note = _score_with_llm(text)
    if score is None:
        score, note = _score_heuristic(text)

    entry["manufacturing_applicability_score"] = score
    if note:
        entry["research_problem_note"] = note


def postprocess_papers(entries: List[Dict[str, Any]]) -> None:
    """對所有的 entries 進行後處理（評分與痛點標記）。"""
    for entry in entries:
        try:
            postprocess_paper(entry)
        except Exception:
            LOGGER.exception("後處理步驟發生異常，跳過此筆")
