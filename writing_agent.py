import openai
import anthropic as _anthropic
import re

from models import ResearchOutput
from config import WRITING_MODEL, WRITING_MAX_TOKENS, WRITING_SYSTEM_PROMPT


def _chat(system: str, user: str, model: str = WRITING_MODEL, max_tokens: int = WRITING_MAX_TOKENS) -> str:
    if model.startswith("claude"):
        client = _anthropic.Anthropic()
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return (resp.content[0].text or "").strip()
    else:
        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return (resp.choices[0].message.content or "").strip()

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
# 논문 제목 형식 「...」 존재 여부 확인
_PAPER_TITLE_RE = re.compile(r'「[^」]+」')

_VAGUE_CITATION_RE = re.compile(
    r'(?:'
    r'\d{4}년의?\s*연구에\s*따르면'          # "2023년 연구에 따르면"
    r'|\d{4}년\s*연구에서[는은]'             # "2024년 연구에서는"
    r'|\d{4}년\s*임상.*?에\s*따르면'        # "2025년 임상 데이터에 따르면"
    r'|최근\s*연구\s*\(\d{4}\)'             # "최근 연구(2023)"
    r'|한\s*연구에[서를]'                   # "한 연구에서"
    r'|한\s*연구에\s*따르면'                # "한 연구에 따르면"
    r'|일부\s*연구에'                       # "일부 연구에"
    r'|최근\s*연구.*?에\s*따르면'           # "최근 연구에 따르면"
    r'|최근\s*연구\s*보고서에\s*따르면'     # "최신 연구 보고서에 따르면"
    r'|최신\s*연구\s*보고서에\s*따르면'     # "최신 연구 보고서에 따르면"
    r'|연구\s*결과에\s*따르면'              # "연구 결과에 따르면"
    r'|연구에\s*따르면'                     # "연구에 따르면" (단독 — 논문 제목 없이)
    r'|많은\s*연구들[은이]'                 # "많은 연구들은"
    r'|전문가들[은이]'                      # "전문가들은"
    r'|세계적\s*[가-힣\s]{0,10}저널'       # "세계적 피부과 저널"
    r'|[가-힣]{2,8}\s*저널에\s*따르면'     # "피부과 저널에 따르면"
    r'|[가-힣]{2,8}\s*학술지에\s*따르면'   # "피부 학술지에 따르면"
    r'|\(출처:\s*최신?\s*연구[^)]*\)'       # "(출처: 최신 연구결과)"
    r'|\(출처:\s*[가-힣A-Za-z\s]{2,30}\)'  # "(출처: XXX)" 형태 가짜 출처
    r')'
)

# 먹는 제품(섭취·경구·복용) 언급 감지
_INGESTION_RE = re.compile(r'섭취|경구\s*복용|복용|먹는\s*보충제|영양제')


def run_writing_agent(research: ResearchOutput) -> str:
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
            "성분표 비교 표와 Pick 추천 섹션에서는 실제 브랜드명 대신 선택 기준(농도·성분 조합·포장·저자극)만 제시하세요.\n"
            "선택 기준은 2~3개만, 각 기준당 100~150자 이내로 간결하게 작성하세요.\n"
            "제품 예시가 없다고 해서 상황별 추가 안내나 부연 설명을 덧붙여 분량을 채우지 마세요."
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
글 길이: 2,500~3,500자
{type_block}
{angle_block}

[임상 인사이트 — 중간 섹션 전체에 반드시 녹여줘]:
{research.key_insights}

{product_block}

위 정보를 바탕으로 시스템 프롬프트의 글 구조와 원칙을 모두 따라 블로그 글을 작성해줘.
- TOPIC_TYPE({research.topic_type})에 맞는 중간 섹션 {section_count}개를 작성할 것.
- EDITORIAL_ANGLE의 "각도 유형"은 오프닝 훅 방향과 각 섹션의 프레이밍 톤에만 반영할 것 (섹션 수·내용은 TOPIC_TYPE 기준).
- 제품 목록에 실제 제품이 있으면 반드시 "어떻게 고르고 시작할까" 섹션에 제품명과 함께 소개할 것.
- 글 전체 최소 2,500자 이상 — 각 중간 섹션은 반드시 300자 이상 작성할 것.
- 300자 미만으로 끝나는 섹션은 KEY_INSIGHTS에서 추가 근거를 1~2단락 더 풀어 써서 반드시 보강할 것. 보강 없이 짧은 섹션을 제출하는 것은 절대 금지.
- 제출 전에 중간 섹션 각각의 분량을 확인하고, 300자 미만이면 반드시 해당 섹션을 보강한 후 제출할 것.
- 본문 문장에서 의문을 표현할 때도 '-까요?' 금지. '~인가', '~인지', '~살펴봐야 합니다' 형태로 작성할 것.
web_search 사용 금지.
""".strip()

    draft = _chat(WRITING_SYSTEM_PROMPT, user_prompt)

    # URL 제외 실제 텍스트 길이로 체크 (가짜 URL이 글자 수를 부풀리는 것 방지)
    draft_text_len = len(_URL_RE.sub('', draft))

    # 글 길이 부족 시 자동 보강 1회
    if draft_text_len < 2500:
        expand_instruction = f"""다음 블로그 글은 현재 {draft_text_len}자입니다 (URL 제외). 목표는 2,500자 이상입니다.
각 중간 섹션(#### 소제목 단위)에서 KEY_INSIGHTS의 임상 근거와 독자 관점 함의를 1~2단락 추가해 보강하세요.
소제목 구조와 전체 흐름은 그대로 유지하고, 내용만 풍부하게 늘립니다.
구어체(-까요?/-요/-죠?) 절대 금지. 격식체로만 작성."""
        draft = run_revision(draft, expand_instruction, threshold=1.0)

    # 출처불명 인용 패턴 감지 시 교정 1회 (볼드 마크다운 제거 후 검사)
    draft_stripped = re.sub(r'\*{1,2}', '', draft)
    if _VAGUE_CITATION_RE.search(draft_stripped):
        draft = _fix_vague_citations(draft)

    # 섭취·경구 복용 등 먹는 제품 언급 감지 시 교정 1회
    if _INGESTION_RE.search(draft):
        draft = _fix_ingestion_content(draft)

    # 허구 저널 인용 감지 시 교정 1회
    valid_urls = _PUBMED_URL_RE.findall(research.key_insights)
    if _has_fabricated_journal_citation(draft, set(valid_urls)):
        draft = _fix_fabricated_citations(draft)

    # 논문이 있었는데 「논문 제목」 형식 인용이 없으면 강제 삽입 1회
    if "URL:" in research.key_insights and not _PAPER_TITLE_RE.search(draft):
        draft = _fix_missing_paper_citations(draft, research.key_insights)

    # 제품이 있는데 글에 누락된 제품 감지 시 교정 1회
    if research.products:
        missing = [p for p in research.products if p.name not in draft]
        if missing:
            draft = _fix_missing_products(draft, missing)

    return draft


def run_revision(draft: str, instruction: str, threshold: float = 0.9) -> str:
    """draft를 instruction에 따라 1회 수정. 원문 대비 글자수가 threshold 미만으로 줄면 원문을 유지한다."""
    fix_prompt = f"""{instruction}

===글===
{draft}
===끝===

수정된 전체 글을 출력하세요."""

    fixed = _chat(WRITING_SYSTEM_PROMPT, fix_prompt)
    fixed_len = len(_URL_RE.sub('', fixed))
    original_len = len(_URL_RE.sub('', draft))
    return fixed if fixed_len >= original_len * threshold else draft


def _fix_vague_citations(draft: str) -> str:
    instruction = """다음 블로그 글에서 출처불명 인용 표현을 찾아 수정하세요.

수정 대상 — 아래 형태가 있으면 반드시 수정 (볼드(**) 처리된 형태도 포함):
- "2023년 연구에 따르면", "**2024년 연구**에 따르면" 등 연도+연구 조합 (볼드 여부 무관)
- "2024년 연구에서는", "2025년 연구에 따르면" 등 연도+연구 모든 변형
- "2025년 임상 데이터에 따르면" 등 연도+임상 형태
- "최근 연구 보고서에 따르면", "최신 연구 보고서에 따르면"
- "최근 연구(2023)에 따르면"
- "한 연구에서", "한 연구에 따르면"
- "일부 연구에 따르면", "최근 연구에 따르면"
- "연구 결과에 따르면", "많은 연구들은"
- "(출처: 최신 연구결과)", "(출처: XXX)" 형태의 모든 괄호 출처 표현
- "세계적 피부과 저널에 따르면" 등 불특정 한국어 저널 표현
- "피부과 저널에 따르면", "피부 학술지에 따르면" 등 모호한 저널 표현

수정 방법:
- "연구에 따르면", "한 연구에서", "연도+연구" 등 인용 도입부를 완전히 제거하고 내용만 직접 서술하세요.
  예: "연구에 따르면 EGF가 세포 재생을 촉진한다" → "EGF는 세포 재생을 촉진합니다"
  예: "2024년 연구에서는 A가 B에 기여하는 것으로 나타났습니다" → "A는 B에 기여합니다"
- 인용에 수치가 포함된 경우 출처 불명 수치도 함께 제거하세요.
- 「논문 제목」(저널명, 연도) 형식의 올바른 인용은 수정하지 마세요.
- 글의 다른 부분(소제목·구조·분량)은 전혀 수정하지 마세요."""
    return run_revision(draft, instruction, threshold=0.9)


def _has_fabricated_journal_citation(draft: str, valid_urls: set) -> bool:
    """저널명 인용이 있는데 KEY_INSIGHTS의 실제 PubMed URL이 글에 없으면 허구 인용으로 판단."""
    if not _JOURNAL_CITATION_RE.search(draft):
        return False
    draft_urls = set(_PUBMED_URL_RE.findall(draft))
    return len(draft_urls & valid_urls) == 0


def _fix_fabricated_citations(draft: str) -> str:
    instruction = """다음 블로그 글에서 출처 URL이 없는 저널명 인용을 찾아 수정하세요.

수정 대상:
- "Journal of XYZ에서 발표한 연구에 따르면..." 형태의 인용 중 URL이 없는 것
- "British Journal of Dermatology에 수록된 연구..." 형태의 인용 중 URL이 없는 것

수정 방법:
- URL 없는 저널명 인용은 "~로 알려져 있습니다", "~가 확인됩니다" 등 서술형으로 바꾸세요.
- 수치가 포함된 경우 수치도 제거하세요.
- 글의 다른 부분(소제목·구조·분량)은 전혀 수정하지 마세요."""
    return run_revision(draft, instruction, threshold=0.9)


def _fix_missing_paper_citations(draft: str, key_insights: str) -> str:
    instruction = f"""다음 블로그 글에 PubMed 논문 인용이 없습니다.
KEY_INSIGHTS에 포함된 논문 중 글 내용과 가장 관련성 높은 것을 1~2개 골라 적절한 위치에 삽입하세요.

인용 형식 (필수):
「논문 제목(영문 그대로)」(저널명, 연도) 형태로 표기
중요: 「」 안에는 반드시 논문 제목을 넣어야 합니다. 저널명을 넣는 것은 금지입니다.
예: 「Ceramide-dominant barrier repair lipids alleviate childhood atopic dermatitis」(Dermatology, 2021)의 연구에서는...

[KEY_INSIGHTS — "제목:" 항목에서 논문 제목을, "저널:" 항목에서 저널명을 가져올 것]:
{key_insights}

규칙:
- 「논문 제목」(저널명, 연도) 이외의 인용 표현("연구에 따르면", "저널에 따르면" 등)은 추가하지 말 것
- 글 구조·소제목·분량은 유지. 논문 인용 문장만 기존 단락에 자연스럽게 추가.
- 삽입 위치는 해당 논문 내용이 가장 자연스럽게 연결되는 섹션을 선택할 것"""
    return run_revision(draft, instruction, threshold=0.9)


def _fix_ingestion_content(draft: str) -> str:
    instruction = """다음 블로그 글에 '섭취', '복용', '경구 복용', '영양제' 등 먹는 제품 관련 내용이 포함되어 있습니다.
이 글은 피부에 바르는 스킨케어 화장품(세럼·크림·앰플 등) 전용 블로그입니다.

수정 방법:
- 섭취·복용·경구 복용 언급이 있는 문장은 바르는 스킨케어 맥락으로 교체하거나 삭제하세요.
- 먹는 방식의 임상 데이터를 인용한 경우, 해당 인용 전체를 삭제하고 같은 성분의 도포 방식 효과를 서술로 대체하세요.
- 글의 구조·소제목·분량은 최대한 유지하세요."""
    return run_revision(draft, instruction, threshold=0.85)


def _fix_missing_products(draft: str, missing) -> str:
    product_lines = "\n".join(
        f"- {p.name}: {p.feature} / {p.price}"
        + (f" / {p.url}" if p.url else "")
        + (f"\n  주요 성분: {p.ingredients}" if p.ingredients else "")
        for p in missing
    )
    instruction = f"""다음 블로그 글의 "어떻게 고르고 시작할까" 섹션에 아래 제품들이 빠져 있습니다. 해당 섹션에 추가해주세요.

누락된 제품:
{product_lines}

각 제품마다 3문장으로 소개합니다:
① 핵심 성분 조합이 주제 성분에 어떻게 작용하는지
② 다른 제품과 구별되는 차별점
③ 어떤 피부 타입·고민에 맞는지

글의 다른 부분(소제목·구조)은 수정하지 마세요."""
    return run_revision(draft, instruction, threshold=0.9)


