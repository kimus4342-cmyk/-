import openai
import random
import re
from rich.console import Console

from models import ResearchOutput, Product
from pubmed_client import search_papers
from topic_history import load_recent_keywords
from naver_trend import get_trend_scores, is_configured as naver_configured
from config import (
    RESEARCH_MODEL,
    RESEARCH_MAX_TOKENS,
    RESEARCH_SYSTEM_PROMPT,
    TOPIC_KEYWORD_PROMPT,
    TOPIC_KEYWORD_MAX_TOKENS,
    TOPIC_SENTENCE_PROMPT,
    TOPIC_SENTENCE_MAX_TOKENS,
    TOPIC_REFINEMENT_PROMPT,
    TOPIC_REFINEMENT_MAX_TOKENS,
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


_TOPIC_CATEGORIES = [
    "미백·기미·칙칙함",
    "주름·탄력·리프팅",
    "보습·수분·피부 장벽",
    "각질·모공·피부결",
    "민감성·홍조·진정",
    "재생·회복·안티에이징",
    "선케어·자외선 차단",
    "눈가·넥·국소 부위 관리",
    "성분 비교·선택 기준",
]


def run_topic_proposal() -> list[dict]:
    """1) 트렌드 키워드 10개 브레인스토밍 → 2) 네이버 최근 상승 지수로 상위 5개 선별
    → 3) 살아남은 키워드로만 주제 문장 완성. 실행마다 랜덤 카테고리로 다양성 확보."""
    client = openai.OpenAI()
    category = random.choice(_TOPIC_CATEGORIES)
    console.print(f"[dim]이번 주제 탐색 카테고리: {category}[/dim]")

    recent_keywords = load_recent_keywords()
    keywords = _propose_keywords(client, category, recent_keywords)
    if not keywords:
        return []

    _attach_naver_scores(keywords)
    top_keywords = _rank_and_trim(keywords)
    return _write_sentences(client, top_keywords)


def _propose_keywords(client: openai.OpenAI, category: str, recent_keywords: list[str]) -> list[dict]:
    history_block = ""
    if recent_keywords:
        history_block = (
            "\n\n아래는 최근에 이미 다룬 키워드입니다. 절대 다시 제안하지 마세요:\n"
            + "\n".join(f"- {k}" for k in recent_keywords)
        )
    response = client.chat.completions.create(
        model=RESEARCH_MODEL,
        max_tokens=TOPIC_KEYWORD_MAX_TOKENS,
        messages=[
            {"role": "system", "content": TOPIC_KEYWORD_PROMPT},
            {"role": "user", "content": f"지금 4050 한국 여성에게 핫한 스킨케어 트렌드를 조사하고 키워드 후보 10개를 제안해줘. 10개 중 2~3개는 [{category}] 관련 유형을 포함하고, 나머지는 다양하게 선택해줘.{history_block}"},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    return _filter_keywords(_parse_blocks(raw), recent_keywords)


def _write_sentences(client: openai.OpenAI, top_keywords: list[dict]) -> list[dict]:
    """네이버 검증을 통과한 키워드들로 주제 문장을 완성한다.
    키워드·유형·네이버 점수는 LLM 출력과 무관하게 원본(top_keywords)을 그대로 신뢰한다."""
    lines = [
        f"{i}. 키워드: {k.get('keyword', '')} | 유형: {k.get('type', '')} | 트렌드 근거: {k.get('reason', '')}"
        for i, k in enumerate(top_keywords, 1)
    ]
    user_content = (
        f"아래 {len(top_keywords)}개 키워드로, 각각 CANDIDATE_1~{len(top_keywords)} 블록을 순서대로 작성해줘 "
        "(키워드·유형은 반드시 그대로 유지):\n" + "\n".join(lines)
    )
    response = client.chat.completions.create(
        model=RESEARCH_MODEL,
        max_tokens=TOPIC_SENTENCE_MAX_TOKENS,
        messages=[
            {"role": "system", "content": TOPIC_SENTENCE_PROMPT},
            {"role": "user", "content": user_content},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    sentences = _parse_blocks(raw)

    result = []
    for i, k in enumerate(top_keywords):
        c = dict(sentences[i]) if i < len(sentences) else {}
        c["keyword"] = k.get("keyword", "")
        c["type"] = k.get("type", "")
        if k.get("naver_score") is not None:
            c["naver_score"] = k["naver_score"]
        result.append(c)
    return result


def run_topic_refinement(topic: str) -> str:
    """주제를 경쟁 콘텐츠 분석 기반으로 심화·각도화한다. 실패 시 원래 주제 반환."""
    client = openai.OpenAI()
    try:
        response = client.chat.completions.create(
            model=RESEARCH_MODEL,
            max_tokens=TOPIC_REFINEMENT_MAX_TOKENS,
            messages=[
                {"role": "system", "content": TOPIC_REFINEMENT_PROMPT},
                {"role": "user", "content": f"주제: {topic}"},
            ],
        )
        refined = (response.choices[0].message.content or "").strip()
        # 너무 짧거나 원래 주제보다 짧으면 원래 주제 반환
        if len(refined) < len(topic) or len(refined) > 80:
            return topic
        return refined
    except Exception:
        return topic


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


_URL_RE = re.compile(r'\(?https?://\S+\)?')
_EXCLUDED_INGREDIENTS = {"레티놀", "히알루론산", "콜라겐", "세라마이드"}


_FIELD_MAP = {
    "주제": "topic",
    "유형": "type",
    "각도": "angle",
    "키워드": "keyword",
    "이유": "reason",
}


def _parse_blocks(raw: str) -> list[dict]:
    """"=== 아무개_N ===" 로 구분되고 "필드: 값" 줄이 나열되는 출력을 공통 파싱한다.
    KEYWORD_N(키워드/유형/이유)과 CANDIDATE_N(주제/유형/각도/키워드/이유) 둘 다 이 형식이라 재사용한다."""
    blocks: list[dict] = []
    current: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("=== ") and line.endswith(" ==="):
            if current:
                blocks.append(current)
            current = {}
            continue
        for kr, en in _FIELD_MAP.items():
            if line.startswith(f"{kr}:"):
                value = line.split(":", 1)[1].strip()
                if en == "reason":
                    value = _URL_RE.sub("", value)
                    value = re.sub(r'[\s\(]+$', '', value).strip()
                current[en] = value
                break
    if current:
        blocks.append(current)
    return blocks


def _filter_keywords(items: list[dict], recent_keywords: list[str]) -> list[dict]:
    """제외 성분 포함, 최근 사용 키워드와 정확히 겹침, 배치 내 중복 키워드를 걸러낸다."""
    recent_set = {k.strip().lower() for k in recent_keywords}
    seen: set[str] = set()
    filtered = []
    for it in items:
        if it.get("type") == "뷰티디바이스":
            continue  # 당분간 화장품 성분/제품 위주로만 진행
        kw = it.get("keyword", "")
        terms = [t.strip() for t in kw.split(",") if t.strip()]
        if not terms:
            continue
        if any(any(ing in t for ing in _EXCLUDED_INGREDIENTS) for t in terms):
            continue
        if any(t.lower() in recent_set for t in terms):
            continue
        key = kw.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        filtered.append(it)
    return filtered


def _attach_naver_scores(candidates: list[dict]) -> None:
    """각 후보에 네이버 데이터랩 40-50대 여성 기준 "최근 상승 지수"(naver_score)를 채워 넣는다.
    100=변화 없음, 100 초과=최근 상승. "A, B" 형태의 비교 키워드는 서로 다른 성분이라
    한 그룹에 합치면 조회가 깨지므로, 항목별로 별도 그룹 조회한 뒤 후보당 최댓값을 대표 점수로 사용한다.
    API 미설정·요청 실패 시 조용히 건너뛴다 (candidates는 그대로 사용 가능)."""
    if not naver_configured():
        return
    term_groups: dict[str, str] = {}
    owner: dict[str, int] = {}
    for i, c in enumerate(candidates):
        kw = c.get("keyword")
        if not kw:
            continue
        for j, term in enumerate(t.strip() for t in kw.split(",")):
            if not term:
                continue
            key = f"{i}_{j}"
            term_groups[key] = term
            owner[key] = i

    scores = get_trend_scores(term_groups)
    if not scores:
        console.print("[dim]네이버 데이터랩 조회 실패 또는 결과 없음 — 관심도 정보 없이 진행[/dim]")
        return

    per_candidate: dict[int, list[float]] = {}
    for key, score in scores.items():
        idx = owner.get(key)
        if idx is not None:
            per_candidate.setdefault(idx, []).append(score)
    for i, c in enumerate(candidates):
        values = per_candidate.get(i)
        if values:
            c["naver_score"] = round(max(values), 1)


_FINAL_CANDIDATE_COUNT = 5


def _rank_and_trim(candidates: list[dict], keep: int = _FINAL_CANDIDATE_COUNT) -> list[dict]:
    """네이버 관심도가 있으면 높은 순으로 정렬해 상위 keep개만 남긴다.
    점수가 하나도 없으면 (미설정·조회 실패) LLM이 제시한 원래 순서 그대로 앞에서부터 keep개를 쓴다."""
    scored = [c for c in candidates if c.get("naver_score") is not None]
    if not scored:
        return candidates[:keep]
    ranked = sorted(candidates, key=lambda c: c.get("naver_score", -1), reverse=True)
    return ranked[:keep]


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

    # 제품 섹션 raw 출력 로그
    raw_products_lines = sections.get("PRODUCTS", [])
    if raw_products_lines:
        console.print("[dim]─── PRODUCTS raw 출력 ───[/dim]")
        for l in raw_products_lines:
            if l.strip():
                console.print(f"[dim]{l}[/dim]")
        console.print("[dim]─────────────────────────[/dim]")
    else:
        console.print("[yellow]PRODUCTS 섹션 자체가 없음 — 모델이 섹션을 출력하지 않았습니다[/yellow]")

    products: list[Product] = []
    for line in raw_products_lines:
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
        else:
            console.print(f"[yellow]제품 파싱 실패 (구분자 부족, {len(parts)}개): {line[:80]}[/yellow]")

    valid_products = [p for p in products if not _is_placeholder(p.name)]
    if len(valid_products) < len(products):
        console.print(f"[yellow]경고: 플레이스홀더 제품명 {len(products) - len(valid_products)}개 감지 — 제외됨[/yellow]")
        for p in products:
            if _is_placeholder(p.name):
                console.print(f"[yellow]  필터됨: {p.name}[/yellow]")
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
