import openai

from models import ResearchOutput
from config import WRITING_MODEL, WRITING_MAX_TOKENS, WRITING_SYSTEM_PROMPT


def run_writing_agent(research: ResearchOutput) -> str:
    client = openai.OpenAI()

    product_lines = "\n".join(
        f"  {i + 1}. {p.name} — {p.feature} — {p.price} — {p.url}"
        for i, p in enumerate(research.products)
    )

    user_prompt = f"""
주제: {research.topic}
타겟 독자: 40-50대 한국 여성 (피부 고민: {research.skin_concern})
핵심 메시지: {research.core_message}
추천 제품: 아래 목록 참고
피해야 할 표현: 과장 광고, 단정적 표현, 즉각 효과 주장
글 길이: 1,500~2,500자

[임상 인사이트 — 반드시 섹션 2~3에 녹여줘]:
{research.key_insights}

[추천 제품 목록]:
{product_lines}

위 정보를 바탕으로 시스템 프롬프트의 글 구조와 원칙을 모두 따라 블로그 글을 작성해줘.
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
