import openai
import re

from models import EnhancementResult, ResearchOutput
from writing_agent import _VAGUE_CITATION_RE, _fix_vague_citations, _INGESTION_RE, _fix_ingestion_content, run_revision

_URL_RE = re.compile(r'https?://\S+')
from config import (
    ENHANCEMENT_SEARCH_MODEL,
    ENHANCEMENT_MODEL,
    ENHANCEMENT_SEARCH_MAX_TOKENS,
    ENHANCEMENT_MAX_TOKENS,
    ENHANCEMENT_SEARCH_PROMPT,
    ENHANCEMENT_APPLY_PROMPT,
)


def run_enhancement_agent(article: str, research: ResearchOutput) -> EnhancementResult:
    client = openai.OpenAI()

    # Pass 1: 웹 검색으로 트렌드·SEO·경쟁 분석
    search_user_prompt = f"""
주제: {research.topic}

=== 현재 완성된 글 (참고용) ===
{article[:2000]}{'...(이하 생략)' if len(article) > 2000 else ''}
""".strip()

    search_response = client.chat.completions.create(
        model=ENHANCEMENT_SEARCH_MODEL,
        max_tokens=ENHANCEMENT_SEARCH_MAX_TOKENS,
        messages=[
            {"role": "system", "content": ENHANCEMENT_SEARCH_PROMPT},
            {"role": "user", "content": search_user_prompt},
        ],
    )
    search_raw = (search_response.choices[0].message.content or "").strip()
    trends, seo_keywords, competitor_gaps = _parse_search(search_raw)

    # Pass 2: 분석 결과를 글에 반영
    apply_user_prompt = f"""
=== 경쟁 분석 결과 ===

[TRENDS]
{trends}

[SEO_KEYWORDS]
{seo_keywords}

[COMPETITOR_GAPS]
{competitor_gaps}

=== 고도화할 글 ===
{article}
""".strip()

    apply_response = client.chat.completions.create(
        model=ENHANCEMENT_MODEL,
        max_tokens=ENHANCEMENT_MAX_TOKENS,
        messages=[
            {"role": "system", "content": ENHANCEMENT_APPLY_PROMPT},
            {"role": "user", "content": apply_user_prompt},
        ],
    )
    apply_raw = (apply_response.choices[0].message.content or "").strip()
    enhanced_article = _parse_enhanced(apply_raw, fallback=article)

    # 고도화 후 원문보다 짧아지면 원문 유지 (URL 제외 텍스트 길이 기준)
    if len(_URL_RE.sub('', enhanced_article)) < len(_URL_RE.sub('', article)):
        enhanced_article = article

    # 고도화 에이전트가 새로 삽입한 출처불명 인용·섭취 표현 후처리
    enhanced_stripped = re.sub(r'\*{1,2}', '', enhanced_article)
    if _VAGUE_CITATION_RE.search(enhanced_stripped):
        enhanced_article = _fix_vague_citations(enhanced_article)
    if _INGESTION_RE.search(enhanced_article):
        enhanced_article = _fix_ingestion_content(enhanced_article)

    # 글자수 상한(3,500자) 초과 시 압축 — 검수 단계로 넘어가는 부담도 함께 줄인다
    if len(_URL_RE.sub('', enhanced_article)) > 3500:
        shrink_instruction = """다음 블로그 글은 목표 분량(2,500~3,500자)을 초과했습니다. 3,500자 이내로 압축하세요.

압축 방법:
- 다른 섹션과 내용이 겹치는 섹션이 있으면 삭제하거나 겹치지 않는 섹션에 흡수시키세요.
- 구체적 근거 없이 일반론만 나열하는 문단은 삭제하세요.
- 핵심 기전 설명, 논문 인용, 수치, 소제목 구조, 고정 요소(오프닝·이런 분께 특히 맞습니다·어떻게 고르고 시작할까·마무리)는 삭제하지 말고 유지하세요."""
        enhanced_article = run_revision(enhanced_article, shrink_instruction, threshold=0.5)

    return EnhancementResult(
        trends_found=trends,
        seo_keywords=seo_keywords,
        competitor_gaps=competitor_gaps,
        enhanced_article=enhanced_article,
    )


def _parse_search(raw: str) -> tuple[str, str, str]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in raw.splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            current = line[4:-4].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    trends = "\n".join(sections.get("TRENDS", [])).strip()
    seo_keywords = "\n".join(sections.get("SEO_KEYWORDS", [])).strip()
    competitor_gaps = "\n".join(sections.get("COMPETITOR_GAPS", [])).strip()

    return trends or "조사 결과 없음", seo_keywords or "조사 결과 없음", competitor_gaps or "조사 결과 없음"


def _parse_enhanced(raw: str, fallback: str) -> str:
    sections: dict[str, list[str]] = {}
    current = None
    for line in raw.splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            current = line[4:-4].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    enhanced = "\n".join(sections.get("ENHANCED_ARTICLE", [])).strip()
    return enhanced or fallback
