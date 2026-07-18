# topic_history.py — 과거에 실제로 완성한 글의 주제·키워드를 기록/조회 (중복 방지용)

import json
import os
from datetime import datetime

_HISTORY_FILE = os.path.join(os.path.dirname(__file__), "topic_history.json")
_MAX_ENTRIES = 200
_RECENT_FOR_PROMPT = 60


def load_recent_keywords(limit: int = _RECENT_FOR_PROMPT) -> list[str]:
    """최근 사용된 키워드(성분·비교쌍의 각 항목)를 평탄화해서 반환. 예: "레티날, 비타민C" -> ["레티날", "비타민C"]"""
    if not os.path.exists(_HISTORY_FILE):
        return []
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    terms: list[str] = []
    for entry in history[-limit:]:
        kw = entry.get("keyword", "")
        terms.extend(t.strip() for t in kw.split(",") if t.strip())
    return terms


def record_topic(topic: str, keyword: str = "") -> None:
    history = []
    if os.path.exists(_HISTORY_FILE):
        try:
            with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            history = []
    history.append({"topic": topic, "keyword": keyword, "date": datetime.now().strftime("%Y-%m-%d")})
    history = history[-_MAX_ENTRIES:]
    with open(_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
