import openai
import re

from models import ResearchOutput
from config import WRITING_MODEL, WRITING_MAX_TOKENS, WRITING_SYSTEM_PROMPT

_URL_RE = re.compile(r'https?://\S+')


def run_writing_agent(research: ResearchOutput) -> str:
    client = openai.OpenAI()

    if research.products:
        product_lines = "\n".join(
            f"  {i + 1}. {p.name} — {p.feature} — {p.price} — {p.url}"
            + (f"\n     주요 성분: {p.ingredients}" if p.ingredients else "")
            for i, p in enumerate(research.products)
        )
        product_block = (
            f"[추천 제품 목록 — 성분 포함]:\n{product_lines}\n\n"
            "Pick 추천 섹션 작성 지침:\n"
            "- 각 제품마다 반드시 3문장으로 소개합니다.\n"
            "  ① 이 제품의 핵심 성분 조합과 농도가 주제 성분에 어떻게 작용하는지\n"
            "  ② 다른 제품과 구별되는 이 제품만의 차별점 (포장·농도·조합·사용감 등)\n"
            "  ③ 어떤 피부 타입·고민에 가장 잘 맞는지\n"
            "- 제품명을 첫 문장에 반드시 명시합니다.\n"
            "- 성분표의 '주요 성분'을 근거로 작성하고, 근거 없는 효과 주장은 금지합니다."
        )
    else:
        product_block = (
            "[추천 제품 목록]: 실제 제품 정보를 확보하지 못했습니다.\n"
            "절대로 '제품 A', '제품 B', '제품 C' 같은 플레이스홀더나 가상의 제품명을 만들지 마세요.\n"
            "성분표 비교 표와 Pick 추천 섹션에서는 실제 브랜드명 대신 선택 기준(농도·성분 조합·포장·저자극)만 제시하세요."
        )

    _SECTION_COUNT = {"성분심화": 3, "카테고리비교": 3, "고민해결": 4, "뷰티디바이스": 4}
    section_count = _SECTION_COUNT.get(research.topic_type, 3)

    type_block = f"\n[주제 유형]: {research.topic_type}" if research.topic_type else ""
    angle_block = f"\n[글 각도 — 오프닝 훅·섹션 톤 참고용]:\n{research.editorial_angle}" if research.editorial_angle else ""

    user_prompt = f"""
주제: {research.topic}
[중요] 이 글은 피부에 바르는 스킨케어 화장품에 관한 글입니다. 먹는 보충제·경구 복용 제품은 절대 다루지 마세요.
타겟 독자: 40-50대 한국 여성 (피부 고민: {research.skin_concern})
핵심 메시지: {research.core_message}
피해야 할 표현: 과장 광고, 단정적 표현, 즉각 효과 주장
글 길이: 3,000~4,000자
{type_block}
{angle_block}

[임상 인사이트 — 중간 섹션 전체에 반드시 녹여줘]:
{research.key_insights}

{product_block}

위 정보를 바탕으로 시스템 프롬프트의 글 구조와 원칙을 모두 따라 블로그 글을 작성해줘.
- TOPIC_TYPE({research.topic_type})에 맞는 중간 섹션 {section_count}개를 작성할 것.
- EDITORIAL_ANGLE의 "각도 유형"은 오프닝 훅 방향과 각 섹션의 프레이밍 톤에만 반영할 것 (섹션 수·내용은 TOPIC_TYPE 기준).
- 제품 목록에 실제 제품이 있으면 반드시 "어떻게 고르고 시작할까" 섹션에 제품명과 함께 소개할 것.
- 글 전체 최소 3,000자 이상 — 각 중간 섹션은 반드시 500자 이상 작성할 것.
- 500자 미만으로 끝나는 섹션은 KEY_INSIGHTS에서 추가 근거를 1~2단락 더 풀어 써서 반드시 보강할 것. 보강 없이 짧은 섹션을 제출하는 것은 절대 금지.
- 제출 전에 중간 섹션 각각의 분량을 확인하고, 500자 미만이면 반드시 해당 섹션을 보강한 후 제출할 것.
- 본문 문장에서 의문을 표현할 때도 '-까요?' 금지. '~인가', '~인지', '~살펴봐야 합니다' 형태로 작성할 것.
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
    draft = (response.choices[0].message.content or "").strip()

    # URL 제외 실제 텍스트 길이로 체크 (가짜 URL이 글자 수를 부풀리는 것 방지)
    draft_text_len = len(_URL_RE.sub('', draft))

    # 글 길이 부족 시 자동 보강 1회
    if draft_text_len < 2800:
        expand_prompt = f"""다음 블로그 글은 현재 {draft_text_len}자입니다 (URL 제외). 목표는 3,000자 이상입니다.
각 중간 섹션(#### 소제목 단위)에서 KEY_INSIGHTS의 임상 근거와 독자 관점 함의를 1~2단락 추가해 보강하세요.
소제목 구조와 전체 흐름은 그대로 유지하고, 내용만 풍부하게 늘립니다.
구어체(-까요?/-요/-죠?) 절대 금지. 격식체로만 작성.

===글 원문===
{draft}
===끝===

보강된 전체 글을 출력하세요."""

        expand_response = client.chat.completions.create(
            model=WRITING_MODEL,
            max_tokens=WRITING_MAX_TOKENS,
            messages=[
                {"role": "system", "content": WRITING_SYSTEM_PROMPT},
                {"role": "user", "content": expand_prompt},
            ],
        )
        expanded = (expand_response.choices[0].message.content or "").strip()
        expanded_text_len = len(_URL_RE.sub('', expanded))
        if expanded_text_len > draft_text_len:
            draft = expanded

    return draft
