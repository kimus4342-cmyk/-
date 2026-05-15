import openai

from models import EnhancementResult, ResearchOutput
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
