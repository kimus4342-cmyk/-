import openai
from rich.console import Console

from models import ResearchOutput, Product
from config import RESEARCH_MODEL, RESEARCH_MAX_TOKENS, RESEARCH_SYSTEM_PROMPT

console = Console(legacy_windows=False)

_USER_PROMPT = "지금 4050 한국 여성에게 가장 핫한 화장품 성분 트렌드를 조사하고 주제를 하나 선정해줘."


def run_research_agent() -> ResearchOutput:
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model=RESEARCH_MODEL,
        max_tokens=RESEARCH_MAX_TOKENS,
        messages=[
            {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
            {"role": "user", "content": _USER_PROMPT},
        ],
    )
    raw = response.choices[0].message.content or ""
    return _parse(raw.strip())


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

    products: list[Product] = []
    for line in sections.get("PRODUCTS", []):
        line = line.strip()
        if not line or not line[0].isdigit():
            continue
        # "1. name | feature | price | url"
        body = line.split(".", 1)[1].strip() if "." in line else line
        parts = [p.strip() for p in body.split("|")]
        if len(parts) >= 4:
            products.append(Product(
                name=parts[0],
                feature=parts[1],
                price=parts[2],
                url=parts[3],
            ))

    if not topic:
        console.print("[yellow]경고: 리서치 출력 파싱 실패, 원문을 key_insights로 저장[/yellow]")
        topic = "미분류 주제"
        key_insights = raw

    return ResearchOutput(
        topic=topic,
        skin_concern=skin_concern,
        core_message=core_message,
        key_insights=key_insights,
        products=products,
    )
