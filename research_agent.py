import openai
from rich.console import Console

from models import ResearchOutput, Product
from config import (
    RESEARCH_MODEL,
    RESEARCH_MAX_TOKENS,
    RESEARCH_SYSTEM_PROMPT,
    TOPIC_PROPOSAL_PROMPT,
    TOPIC_PROPOSAL_MAX_TOKENS,
)

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
    response = client.chat.completions.create(
        model=RESEARCH_MODEL,
        max_tokens=RESEARCH_MAX_TOKENS,
        messages=[
            {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
            {"role": "user", "content": f"선정된 주제: {topic}\n\n이 주제로 리서치를 진행해줘."},
        ],
    )
    raw = response.choices[0].message.content or ""
    return _parse(raw.strip())


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
        elif line.startswith("각도:"):
            current["angle"] = line.split(":", 1)[1].strip()
        elif line.startswith("이유:"):
            current["reason"] = line.split(":", 1)[1].strip()
    if current:
        candidates.append(current)
    return candidates


def _parse(raw: str) -> ResearchOutput:
    sections: dict[str, list[str]] = {}
    current = None
    for line in raw.splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            current = line[4:-4].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    topic = "\n".join(sections.get("TOPIC", [])).strip()
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
                url=parts[3],
                ingredients=parts[4] if len(parts) >= 5 else "",
            ))

    valid_products = [p for p in products if not _is_placeholder(p.name)]
    if len(valid_products) < len(products):
        console.print(f"[yellow]경고: 플레이스홀더 제품명 {len(products) - len(valid_products)}개 감지 — 제외됨[/yellow]")
    products = valid_products

    if not topic:
        console.print("[yellow]경고: 리서치 출력 파싱 실패, 원문을 key_insights로 저장[/yellow]")
        topic = "미분류 주제"
        key_insights = raw

    return ResearchOutput(
        topic=topic,
        skin_concern=skin_concern,
        core_message=core_message,
        key_insights=key_insights,
        editorial_angle=editorial_angle,
        products=products,
    )
