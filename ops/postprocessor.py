"""論文後處理模組：對 papers 類別進行 manufacturing applicability 評分。"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List

LOGGER = logging.getLogger("postprocessor")

# 製造業相關關鍵字
MANUFACTURING_KEYWORDS = [
    "manufactur", "sensor", "cnc", "robot", "assembly",
    "digital twin", "predictive maintenance", "cad", "cam",
]


def _score_heuristic(text: str) -> tuple[int, str]:
    """啟發式規則：依關鍵字命中數評分。"""
    hits = sum(1 for kw in MANUFACTURING_KEYWORDS if kw in text)
    score = min(100, 20 + hits * 20)

    notes: List[str] = []
    if "sensor" in text:
        notes.append("sensor integration likely")
    if "cad" in text or "cam" in text:
        notes.append("CAD/CAM relevance")
    note = "; ".join(notes) or "No clear sensor/CAD integration detected"

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
            f"請基於以下論文標題與摘要，給出一個 0-100 的 'manufacturing applicability' 分數，"
            f"並在一到兩句話中說明是否涉及感測器整合或 CAD/CAM 集成（返回純文字）。\n\n{text}"
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
        entry["sensor_cad_integration_note"] = note


def postprocess_papers(entries: List[Dict[str, Any]]) -> None:
    """對所有 papers 類別的 entries 進行後處理。"""
    for entry in entries:
        if (entry.get("category") or "").lower() == "papers":
            try:
                postprocess_paper(entry)
            except Exception:
                LOGGER.exception("論文後處理步驟發生異常，跳過此筆")
