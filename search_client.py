# search_client.py — 실제 웹 검색이 필요한 호출 전용 공통 헬퍼
#
# gpt-4o-mini-search-preview를 chat.completions.create()로 호출하던 기존 방식은
# 검증 결과 실제 검색 없이 그럴듯한 값을 지어내는 것으로 확인됐다 (annotations 항상 빈 배열,
# 실시간 값 질의에 출처 없는 부정확한 답변 반환). 이 모듈은 Responses API +
# tools=[{"type": "web_search"}] 조합으로만 호출해 실제 검색을 강제한다.
#
# RESEARCH_MODEL·ENHANCEMENT_SEARCH_MODEL·REVIEW_COLLECTOR_MODEL처럼 프롬프트에
# "web_search를 실행하라"는 지시가 있는 모든 호출은 반드시 이 함수를 통해야 한다.

import openai


def search_completion(model: str, system: str, user: str, max_output_tokens: int | None = None) -> str:
    """web_search 도구를 활성화한 Responses API 호출. 최종 텍스트만 반환한다."""
    client = openai.OpenAI()
    kwargs = {
        "model": model,
        "instructions": system,
        "input": user,
        "tools": [{"type": "web_search"}],
    }
    if max_output_tokens:
        kwargs["max_output_tokens"] = max_output_tokens
    response = client.responses.create(**kwargs)
    return (response.output_text or "").strip()
