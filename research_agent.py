import openai
from rich.console import Console

from models import ResearchOutput, Product
from pubmed_client import search_papers
from config import (
    RESEARCH_MODEL,
    RESEARCH_MAX_TOKENS,
    RESEARCH_SYSTEM_PROMPT,
    TOPIC_PROPOSAL_PROMPT,
    TOPIC_PROPOSAL_MAX_TOKENS,
)

# PubMed는 영어 검색이므로 주요 성분명 매핑
_KR_TO_PUBMED: dict[str, str] = {
    "히알루론산": "hyaluronic acid skin aging",
    "레티놀": "retinol skin aging women",
    "나이아신아마이드": "niacinamide skin hyperpigmentation",
    "비타민c": "vitamin C ascorbic acid skin aging",
    "비타민 c": "vitamin C ascorbic acid skin aging",
    "펩타이드": "peptide skin aging collagen",
    "세라마이드": "ceramide skin barrier",
    "aha": "alpha hydroxy acid skin exfoliation",
    "bha": "salicylic acid skin",
    "pdrn": "polydeoxyribonucleotide skin regeneration",
    "엑소좀": "exosome skin regeneration",
    "egf": "epidermal growth factor skin",
    "판테놀": "panthenol dexpanthenol skin",
    "아데노신": "adenosine wrinkle skin",
    "트레티노인": "tretinoin retinoid skin aging",
    "글리콜산": "glycolic acid skin rejuvenation",
    "코엔자임q10": "coenzyme Q10 skin aging",
    "콜라겐": "collagen skin aging supplementation",
    "스쿠알란": "squalane skin moisturizer",
    "아르부틴": "arbutin melanin skin whitening",
    "트라넥삼산": "tranexamic acid melasma skin",
}


def _pubmed_query(topic: str) -> str:
    lower = topic.lower()
    for kr, en in _KR_TO_PUBMED.items():
        if kr in lower:
            return en
    return topic

console = Console(legacy_windows=False)

_PLACEHOLDER_NAMES = {"제품 a", "제품 b", "제품 c", "제품a", "제품b", "제품c"}
_PLACEHOLDER_KEYWORDS = ["브랜드명", "제품명", "정확한", "플레이스홀더", "브랜드 +", "example", "sample"]


def _is_placeholder(name: str) -> bool:
    n = name.strip().lower()
    if n in _PLACEHOLDER_NAMES:
        return True
    if n.startswith("[") or n.startswith("("):
        return True
    return any(kw in n for kw in _PLACEHOLDER_KEYWORDS)


def _sanitize_url(url: str) -> str:
    """300자 초과이거나 0이 20개 이상 연속되면 가짜 URL로 판단해 빈 문자열 반환."""
    if len(url) > 300:
        return ""
    if "0" * 20 in url:
        return ""
    return url


def run_topic_proposal() -> list[dict]:
    """주제 후보 3개를 제안하고 반환."""
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model=RESEARCH_MODEL,
        max_tokens=TOPIC_PROPOSAL_MAX_TOKENS,
        messages=[
            {"role": "system", "content": TOPIC_PROPOSAL_PROMPT},
            {"role": "user", "content": "지금 4050 한국 여성에게 핫한 스킨케어 트렌드를 조사하고 주제 후보 3개를 제안해줘."},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    return _parse_candidates(raw)


def run_research_agent(topic: str) -> ResearchOutput:
    """선택된 주제로 전체 리서치 수행."""
    client = openai.OpenAI()

    papers = search_papers(_pubmed_query(topic), max_results=4)
    if papers:
        console.print(f"[dim]PubMed 논문 {len(papers)}편 확보[/dim]")
        paper_block = "=== PubMed 논문 목록 ===\n" + "\n".join(p.format_for_prompt() for p in papers)
    else:
        console.print("[dim]PubMed 논문 없음 — 기전 설명 위주로 진행[/dim]")
        paper_block = "(제공된 PubMed 논문 없음)"

    user_content = f"선정된 주제: {topic} (피부에 바르는 스킨케어 화장품 기준, 먹는 보충제 제외)\n\n{paper_block}\n\n이 주제로 리서치를 진행해줘."

    response = client.chat.completions.create(
        model=RESEARCH_MODEL,
        max_tokens=RESEARCH_MAX_TOKENS,
        messages=[
            {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    raw = response.choices[0].message.content or ""
    return _parse(raw.strip(), fallback_topic=topic)


def _parse_candidates(raw: str) -> list[dict]:
    candidates = []
    current: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("=== CANDIDATE_") and line.endswith(" ==="):
            if current:
                candidates.append(current)
            current = {}
        elif line.startswith("주제:"):
            current["topic"] = line.split(":", 1)[1].strip()
        elif line.startswith("유형:"):
            current["type"] = line.split(":", 1)[1].strip()
        elif line.startswith("각도:"):
            current["angle"] = line.split(":", 1)[1].strip()
        elif line.startswith("이유:"):
            current["reason"] = line.split(":", 1)[1].strip()
    if current:
        candidates.append(current)
    return candidates


def _parse(raw: str, fallback_topic: str = "") -> ResearchOutput:
    sections: dict[str, list[str]] = {}
    current = None
    for line in raw.splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            current = line[4:-4].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    topic = "\n".join(sections.get("TOPIC", [])).strip()
    topic_type = "\n".join(sections.get("TOPIC_TYPE", [])).strip()
    skin_concern = "\n".join(sections.get("SKIN_CONCERN", [])).strip()
    core_message = "\n".join(sections.get("CORE_MESSAGE", [])).strip()
    key_insights = "\n".join(sections.get("KEY_INSIGHTS", [])).strip()
    editorial_angle = "\n".join(sections.get("EDITORIAL_ANGLE", [])).strip()

    products: list[Product] = []
    for line in sections.get("PRODUCTS", []):
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        body = line.split(".", 1)[1].strip() if "." in line else line
        parts = [p.strip() for p in body.split("|")]
        if len(parts) >= 4:
            products.append(Product(
                name=parts[0],
                feature=parts[1],
                price=parts[2],
                url=_sanitize_url(parts[3]),
                ingredients=parts[4] if len(parts) >= 5 else "",
            ))

    valid_products = [p for p in products if not _is_placeholder(p.name)]
    if len(valid_products) < len(products):
        console.print(f"[yellow]경고: 플레이스홀더 제품명 {len(products) - len(valid_products)}개 감지 — 제외됨[/yellow]")
    products = valid_products

    if not topic:
        if fallback_topic:
            console.print("[yellow]경고: TOPIC 섹션 파싱 실패 — 입력 주제로 대체합니다[/yellow]")
            topic = fallback_topic
        else:
            console.print("[yellow]경고: 리서치 출력 파싱 실패, 원문을 key_insights로 저장[/yellow]")
            topic = "미분류 주제"
            key_insights = raw

    return ResearchOutput(
        topic=topic,
        topic_type=topic_type,
        skin_concern=skin_concern,
        core_message=core_message,
        key_insights=key_insights,
        editorial_angle=editorial_angle,
        products=products,
    )
