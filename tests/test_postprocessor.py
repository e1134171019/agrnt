"""test_postprocessor.py — 測試 manufacturing applicability 後處理邏輯。"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from ops.postprocessor import (
    _score_heuristic,
    postprocess_paper,
    postprocess_papers,
)


class TestScoreHeuristic:
    def test_no_keywords_base_score(self) -> None:
        score, note = _score_heuristic("some random text about weather")
        assert score == 20
        assert "No clear sensor/CAD" in note

    def test_sensor_keyword(self) -> None:
        score, note = _score_heuristic("sensor fusion for temperature monitoring")
        assert score == 40  # 20 + 1*20
        assert "sensor integration likely" in note

    def test_cad_keyword(self) -> None:
        score, note = _score_heuristic("cad software update for design")
        assert score == 40
        assert "CAD/CAM relevance" in note

    def test_multiple_keywords(self) -> None:
        score, _ = _score_heuristic("manufacturing sensor cnc robot assembly")
        assert score == 100  # 20 + 5*20 = 120 → capped at 100

    def test_cam_keyword(self) -> None:
        _, note = _score_heuristic("cam machining process")
        assert "CAD/CAM relevance" in note


class TestPostprocessPaper:
    def test_heuristic_mode(self) -> None:
        entry = {
            "title": "Sensor Fusion for CNC Machines",
            "summary_raw": "A study on sensor integration in manufacturing.",
            "category": "papers",
        }
        with patch.dict("os.environ", {}, clear=True):
            postprocess_paper(entry)
        assert "manufacturing_applicability_score" in entry
        assert entry["manufacturing_applicability_score"] >= 20
        assert "sensor_cad_integration_note" in entry

    def test_llm_mode_success(self) -> None:
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Score: 85. This paper discusses sensor integration."
        mock_client.return_value.chat.completions.create.return_value = mock_resp

        entry = {
            "title": "AI in Manufacturing",
            "summary_raw": "Using AI for quality control.",
            "category": "papers",
        }
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), \
             patch("ops.postprocessor.OpenAI", mock_client, create=True):
            # 因為 _score_with_llm 內部 import，需要 mock 正確位置
            from unittest.mock import patch as _patch
            with _patch("ops.postprocessor.OpenAI", mock_client, create=True):
                postprocess_paper(entry)
        assert "manufacturing_applicability_score" in entry

    def test_llm_failure_falls_back_to_heuristic(self) -> None:
        entry = {
            "title": "Robot Assembly Line",
            "summary_raw": "Predictive maintenance with sensor.",
            "category": "papers",
        }
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}), \
             patch("ops.postprocessor.OpenAI", side_effect=Exception("API down"), create=True):
            postprocess_paper(entry)
        # 即使 LLM 失敗也應該有分數（來自 heuristic fallback）
        assert "manufacturing_applicability_score" in entry


class TestPostprocessPapers:
    def test_only_processes_papers_category(self) -> None:
        entries = [
            {"title": "News Article", "summary_raw": "Some news", "category": "news"},
            {"title": "Sensor Paper", "summary_raw": "Manufacturing sensor", "category": "papers"},
        ]
        with patch.dict("os.environ", {}, clear=True):
            postprocess_papers(entries)
        # news 不應有 manufacturing_applicability_score
        assert "manufacturing_applicability_score" not in entries[0]
        # papers 應有
        assert "manufacturing_applicability_score" in entries[1]

    def test_empty_entries(self) -> None:
        postprocess_papers([])  # 不應 raise

    def test_exception_in_single_entry_doesnt_crash(self) -> None:
        entries = [
            {"title": None, "summary_raw": None, "category": "papers"},
        ]
        # 即使 entry 有誤也不應 crash
        postprocess_papers(entries)
