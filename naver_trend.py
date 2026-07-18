# naver_trend.py — NAVER API HUB 검색어트렌드 API (40-50대 여성 검색 관심도 조회)

import json
import os
import urllib.request
from datetime import date, timedelta

_ENDPOINT = "https://naverapihub.apigw.ntruss.com/search-trend/v1/search"
_AGES_40_50 = ["7", "8", "9", "10"]  # 40-44, 45-49, 50-54, 55-59
_MAX_GROUPS = 5  # 데이터랩 API 1회 요청당 키워드 그룹 최대 개수


def is_configured() -> bool:
    return bool(os.getenv("NAVER_CLIENT_ID") and os.getenv("NAVER_CLIENT_SECRET"))


def get_trend_scores(keyword_by_group: dict[str, str], months: int = 6) -> dict[str, float]:
    """그룹명 -> 대표 키워드 매핑을 받아, 40-50대 여성 기준 "최근 상승 지수"를 반환.
    100 = 최근 1개월이 이전 기간 평균과 동일, 100 초과 = 최근 상승, 100 미만 = 하락.
    (꾸준히 검색량이 많기만 한 "뻔한" 키워드보다, 최근 들어 관심이 오르고 있는 키워드를 우대하기 위함)
    API 키 미설정이거나 요청 실패 시 빈 dict 반환. 그룹이 5개 초과면 여러 번 나눠 호출한다."""
    client_id = os.getenv("NAVER_CLIENT_ID")
    client_secret = os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret or not keyword_by_group:
        return {}

    items = list(keyword_by_group.items())
    scores: dict[str, float] = {}
    for i in range(0, len(items), _MAX_GROUPS):
        scores.update(_query(items[i:i + _MAX_GROUPS], client_id, client_secret, months))
    return scores


def _query(items: list[tuple[str, str]], client_id: str, client_secret: str, months: int) -> dict[str, float]:
    end = date.today()
    start = end - timedelta(days=30 * months)
    body = {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "timeUnit": "month",
        "keywordGroups": [{"groupName": name, "keywords": [kw]} for name, kw in items],
        "gender": "f",
        "ages": _AGES_40_50,
    }

    req = urllib.request.Request(
        _ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "X-NCP-APIGW-API-KEY-ID": client_id,
            "X-NCP-APIGW-API-KEY": client_secret,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception:
        return {}

    scores: dict[str, float] = {}
    for result in data.get("results", []):
        score = _growth_score(result.get("data", []))
        if score is not None:
            scores[result["title"]] = score
    return scores


def _growth_score(points: list[dict]) -> float | None:
    """최근 1개월 관심도가 이전 기간 평균 대비 몇 %인지 반환 (100=변화 없음).
    데이터가 없으면 None, 1개뿐이면 그 값을 그대로 반환."""
    if not points:
        return None
    if len(points) == 1:
        return round(points[0]["ratio"], 1)
    baseline_points, last_point = points[:-1], points[-1]
    baseline = sum(p["ratio"] for p in baseline_points) / len(baseline_points)
    if baseline <= 0:
        return round(last_point["ratio"], 1)
    return round(last_point["ratio"] / baseline * 100, 1)
