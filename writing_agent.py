import openai
import re

from models import ResearchOutput
from config import WRITING_MODEL, WRITING_MAX_TOKENS, WRITING_SYSTEM_PROMPT

_URL_RE = re.compile(r'https?://\S+')

# KEY_INSIGHTS 안의 PubMed URL 추출
_PUBMED_URL_RE = re.compile(r'https?://(?:doi\.org|pubmed\.ncbi\.nlm\.nih\.gov)/\S+')

# 저널명이 포함된 인용 패턴 ("Journal of XYZ에 따르면" 류)
_JOURNAL_CITATION_RE = re.compile(
    r'[A-Z][A-Za-z\s&,]{3,}'
    r'(?:Journal|Dermatology|Cosmetic|Clinical|Investigative|British|American|'
    r'European|International|Science|Research|Medicine|Biology|Pharmacy)'
    r'[A-Za-z\s]*'
    r'(?:에서\s*발표한|에\s*수록된|에\s*실린|에\s*따르면|의\s*연구)'
)

# 출처불명 인용 패턴 — 저널명 없이 "연구에 따르면" 류 표현
_VAGUE_CITATION_RE = re.compile(
    r'(?:'
    r'\d{4}년\s*연구에\s*따르면'      # "2023년 연구에 따르면"
    r'|한\s*연구에[서를]'              # "한 연구에서"
    r'|한\s*연구에\s*따르면'           # "한 연구에 따르면"
    r'|일부\s*연구에'                  # "일부 연구에"
    r'|최근\s*연구.*?에\s*따르면'      # "최근 연구에 따르면"
    r'|연구\s*결과에\s*따르면'         # "연구 결과에 따르면"
    r'|많은\s*연구들[은이]'            # "많은 연구들은"
    r')'
)


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

    # 출처불명 인용 패턴 감지 시 교정 1회
    if _VAGUE_CITATION_RE.search(draft):
        draft = _fix_vague_citations(client, draft)

    # 허구 저널 인용 감지 시 교정 1회
    valid_urls = _PUBMED_URL_RE.findall(research.key_insights)
    if _has_fabricated_journal_citation(draft, set(valid_urls)):
        draft = _fix_fabricated_citations(client, draft)

    # 제품이 있는데 글에 누락된 제품 감지 시 교정 1회
    if research.products:
        missing = [p for p in research.products if p.name not in draft]
        if missing:
            draft = _fix_missing_products(client, draft, missing)

    return draft


def _fix_vague_citations(client: openai.OpenAI, draft: str) -> str:
    fix_prompt = f"""다음 블로그 글에서 출처불명 인용 표현을 찾아 수정하세요.

수정 대상 — 아래 형태가 있으면 반드시 수정:
- "2023년 연구에 따르면" (저널명 없이 연도만)
- "한 연구에서", "한 연구에 따르면"
- "일부 연구에 따르면", "최근 연구에 따르면"
- "연구 결과에 따르면", "많은 연구들은"

수정 방법:
- 저널명·URL 없는 인용은 "~로 알려져 있습니다", "~가 확인됩니다", "~로 이해됩니다" 등 서술형으로 바꾸세요.
- 인용에 수치가 포함된 경우 수치도 함께 제거하세요.
- 저널명이 명시된 인용 ("Journal of XYZ에 따르면" 등)은 수정하지 마세요.
- 글의 다른 부분(소제목·구조·분량)은 전혀 수정하지 마세요.

===글===
{draft}
===끝===

수정된 전체 글을 출력하세요."""

    response = client.chat.completions.create(
        model=WRITING_MODEL,
        max_tokens=WRITING_MAX_TOKENS,
        messages=[
            {"role": "system", "content": WRITING_SYSTEM_PROMPT},
            {"role": "user", "content": fix_prompt},
        ],
    )
    fixed = (response.choices[0].message.content or "").strip()
    # 교정 후 글이 너무 짧아지면 원문 유지
    fixed_text_len = len(_URL_RE.sub('', fixed))
    original_text_len = len(_URL_RE.sub('', draft))
    return fixed if fixed_text_len >= original_text_len * 0.9 else draft


def _has_fabricated_journal_citation(draft: str, valid_urls: set) -> bool:
    """저널명 인용이 있는데 KEY_INSIGHTS의 실제 PubMed URL이 글에 없으면 허구 인용으로 판단."""
    if not _JOURNAL_CITATION_RE.search(draft):
        return False
    draft_urls = set(_PUBMED_URL_RE.findall(draft))
    return len(draft_urls & valid_urls) == 0


def _fix_fabricated_citations(client: openai.OpenAI, draft: str) -> str:
    fix_prompt = f"""다음 블로그 글에서 출처 URL이 없는 저널명 인용을 찾아 수정하세요.

수정 대상:
- "Journal of XYZ에서 발표한 연구에 따르면..." 형태의 인용 중 URL이 없는 것
- "British Journal of Dermatology에 수록된 연구..." 형태의 인용 중 URL이 없는 것

수정 방법:
- URL 없는 저널명 인용은 "~로 알려져 있습니다", "~가 확인됩니다" 등 서술형으로 바꾸세요.
- 수치가 포함된 경우 수치도 제거하세요.
- 글의 다른 부분(소제목·구조·분량)은 전혀 수정하지 마세요.

===글===
{draft}
===끝===

수정된 전체 글을 출력하세요."""

    response = client.chat.completions.create(
        model=WRITING_MODEL,
        max_tokens=WRITING_MAX_TOKENS,
        messages=[
            {"role": "system", "content": WRITING_SYSTEM_PROMPT},
            {"role": "user", "content": fix_prompt},
        ],
    )
    fixed = (response.choices[0].message.content or "").strip()
    fixed_text_len = len(_URL_RE.sub('', fixed))
    original_text_len = len(_URL_RE.sub('', draft))
    return fixed if fixed_text_len >= original_text_len * 0.9 else draft


def _fix_missing_products(client: openai.OpenAI, draft: str, missing) -> str:
    product_lines = "\n".join(
        f"- {p.name}: {p.feature} / {p.price}"
        + (f" / {p.url}" if p.url else "")
        + (f"\n  주요 성분: {p.ingredients}" if p.ingredients else "")
        for p in missing
    )
    fix_prompt = f"""다음 블로그 글의 "어떻게 고르고 시작할까" 섹션에 아래 제품들이 빠져 있습니다. 해당 섹션에 추가해주세요.

누락된 제품:
{product_lines}

각 제품마다 3문장으로 소개합니다:
① 핵심 성분 조합이 주제 성분에 어떻게 작용하는지
② 다른 제품과 구별되는 차별점
③ 어떤 피부 타입·고민에 맞는지

글의 다른 부분(소제목·구조)은 수정하지 마세요.

===글===
{draft}
===끝===

수정된 전체 글을 출력하세요."""

    response = client.chat.completions.create(
        model=WRITING_MODEL,
        max_tokens=WRITING_MAX_TOKENS,
        messages=[
            {"role": "system", "content": WRITING_SYSTEM_PROMPT},
            {"role": "user", "content": fix_prompt},
        ],
    )
    fixed = (response.choices[0].message.content or "").strip()
    fixed_text_len = len(_URL_RE.sub('', fixed))
    original_text_len = len(_URL_RE.sub('', draft))
    return fixed if fixed_text_len >= original_text_len * 0.9 else draft
