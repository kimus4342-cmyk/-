import openai

from models import ResearchOutput
from config import WRITING_MODEL, WRITING_MAX_TOKENS, WRITING_SYSTEM_PROMPT


def run_writing_agent(research: ResearchOutput) -> str:
    client = openai.OpenAI()

    if research.products:
        product_lines = "\n".join(
            f"  {i + 1}. {p.name} — {p.feature} — {p.price} — {p.url}"
            + (f"\n     주요 성분: {p.ingredients}" if p.ingredients else "")
            for i, p in enumerate(research.products)
        )
        product_block = f"[추천 제품 목록 — 성분 포함]:\n{product_lines}"
    else:
        product_block = (
            "[추천 제품 목록]: 실제 제품 정보를 확보하지 못했습니다.\n"
            "절대로 '제품 A', '제품 B', '제품 C' 같은 플레이스홀더나 가상의 제품명을 만들지 마세요.\n"
            "성분표 비교 표와 Pick 추천 섹션에서는 실제 브랜드명 대신 선택 기준(농도·성분 조합·포장·저자극)만 제시하세요."
        )

    angle_block = f"\n[글 각도 — 중간 섹션 구조 선택에 사용]:\n{research.editorial_angle}" if research.editorial_angle else ""

    user_prompt = f"""
주제: {research.topic}
타겟 독자: 40-50대 한국 여성 (피부 고민: {research.skin_concern})
핵심 메시지: {research.core_message}
피해야 할 표현: 과장 광고, 단정적 표현, 즉각 효과 주장
글 길이: 1,500~2,500자
{angle_block}

[임상 인사이트 — 중간 섹션 2~3에 녹여줘]:
{research.key_insights}

{product_block}

위 정보를 바탕으로 시스템 프롬프트의 글 구조와 원칙을 모두 따라 블로그 글을 작성해줘.
- EDITORIAL_ANGLE의 "각도 유형"에 맞는 중간 섹션 구조를 선택할 것.
- 성분표 비교는 반드시 마크다운 표 형식으로 작성하고 제품 목록의 "주요 성분"을 정확히 반영할 것.
web_search 사용 금지.
""".strip()

    response = client.chat.completions.create(
        model=WRITING_MODEL,
        max_tokens=WRITING_MAX_TOKENS,
        messages=[
            {"role": "system", "content": WRITING_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return (response.choices[0].message.content or "").strip()
