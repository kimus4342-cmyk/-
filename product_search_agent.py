import openai
import re

from models import ResearchOutput, Product
from config import RESEARCH_MODEL
from research_agent import _sanitize_url, _is_placeholder

_URL_RE = re.compile(r'https?://\S+')

_SYSTEM_PROMPT = """
You are a Korean beauty product researcher specializing in the 40-50 age group skincare market.

You will be given a completed skincare blog article and its topic/skin concern.
Your job: find 3 real products that best match the article's content and skin concern.

Steps:
1. Read the article to identify: key ingredient, skin concern focus, recommended product type/concentration
2. web_search (최대 2회):
   - 1차: "핵심성분명 올리브영 추천" (제형 무관 — 세럼·크림·마스크팩·앰플·토너 모두 포함)
   - 2차 (결과 부족 시): "핵심성분명 네이버쇼핑 40대 추천"
3. 글의 피부 고민(건성·민감성·홍조 등)에 맞는 제품을 우선 선정

Output EXACTLY in this format — no extra text:

=== PRODUCTS ===
1. 실제브랜드명 실제제품명 | 핵심 성분·특징 | 가격 | 구매링크 | 주요 성분 5가지 이내
2. 실제브랜드명 실제제품명 | 핵심 성분·특징 | 가격 | 구매링크 | 주요 성분 5가지 이내
3. 실제브랜드명 실제제품명 | 핵심 성분·특징 | 가격 | 구매링크 | 주요 성분 5가지 이내

Rules:
- 실제 브랜드명·제품명만 사용. [브랜드명], [제품명] 같은 플레이스홀더 절대 금지.
- 글의 핵심 성분이 실제로 포함된 제품만 추천.
- 저가·중가·고가 고루 포함.
""".strip()


def run_product_search_agent(article: str, research: ResearchOutput) -> list[Product]:
    client = openai.OpenAI()

    user_prompt = f"""
주제: {research.topic}
피부 고민: {research.skin_concern}

=== 완성된 글 (앞부분) ===
{article[:3000]}{'...(이하 생략)' if len(article) > 3000 else ''}

위 글의 내용과 타깃 피부 고민에 맞는 실제 제품 3개를 검색해서 찾아줘.
""".strip()

    response = client.chat.completions.create(
        model=RESEARCH_MODEL,
        max_tokens=1000,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    return _parse(raw)


def _parse(raw: str) -> list[Product]:
    products = []
    in_section = False
    for line in raw.splitlines():
        line = line.strip()
        if line == "=== PRODUCTS ===":
            in_section = True
            continue
        if not in_section or not line or not line[0].isdigit():
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

    return [p for p in products if not _is_placeholder(p.name)]
