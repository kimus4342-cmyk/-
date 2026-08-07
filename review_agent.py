import difflib
import re

from openai import OpenAI
from rich.console import Console

from models import ReviewResult, ResearchOutput
from config import REVIEW_MODEL, REVIEW_MAX_TOKENS, REVIEW_SYSTEM_PROMPT

console = Console(legacy_windows=False)

_CITATION_RE = re.compile(r'「([^」]+)」\s*\(([^,]+),\s*(\d{4})\)')

# LLM이 형식은 지켰지만 근거 없는 인용을 만들어낼 때 자주 쓰는 불특정 출처 표현.
# 24항목 검수(항목16)가 놓쳐도 코드가 한 번 더 잡아내는 백스톱.
_BANNED_PHRASES = [
    "연구에 따르면", "한 연구에서", "한 연구에 따르면", "많은 연구들은", "전문가들은",
    "최근 연구에 따르면", "최신 연구에 따르면", "최근 연구 보고서에 따르면",
    "일부 연구에",
]
_BANNED_YEAR_STUDY_RE = re.compile(r'\d{4}년\s*(임상\s*)?연구(에서는?|에\s*따르면)')


def _check_citations(article: str, known_titles: list[str]) -> list[str]:
    """본문에 인용된 「논문 제목」이 실제 PubMed에서 확보한 목록에 있는지 대조한다.
    표기 차이(공백·구두점 등)를 감안해 유사도 기반으로 비교한다."""
    if not known_titles:
        return []
    warnings = []
    normalized_known = [" ".join(t.lower().split()) for t in known_titles]
    for match in _CITATION_RE.finditer(article):
        cited_title = " ".join(match.group(1).lower().split())
        best_ratio = max(
            (difflib.SequenceMatcher(None, cited_title, known).ratio() for known in normalized_known),
            default=0.0,
        )
        if best_ratio < 0.6:
            warnings.append(f"「{match.group(1)}」({match.group(2)}, {match.group(3)}) — PubMed 확보 목록과 일치하는 논문 없음 (유사도 {best_ratio:.2f})")
    return warnings


def _scan_banned_phrases(article: str) -> list[str]:
    found = [p for p in _BANNED_PHRASES if p in article]
    found += [m.group(0) for m in _BANNED_YEAR_STUDY_RE.finditer(article)]
    return found


def run_review_agent(draft: str, research: ResearchOutput) -> ReviewResult:
    client = OpenAI()

    user_prompt = f"""
주제 "{research.topic}", 독자 40-50대 한국 여성을 위한 다음 글을 검수해줘.
이 글은 트렌드·SEO 반영까지 끝난 발행 직전 최종본이다. 발행 전 마지막 게이트이므로,
고도화 단계에서 새로 추가된 내용(트렌드 데이터, SEO 키워드 줄, 차별화 섹션 포함)도 다른 부분과 동일한 기준으로 검수한다.

=== 리서치 원본 (사실관계 검증 기준) ===
[SKIN_CONCERN]
{research.skin_concern}

[CORE_MESSAGE]
{research.core_message}

[KEY_INSIGHTS]
{research.key_insights}

=== 검수 대상 글 ===
{draft}
""".strip()

    messages = [
        {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    response = client.chat.completions.create(
        model=REVIEW_MODEL,
        max_completion_tokens=REVIEW_MAX_TOKENS,
        messages=messages,
    )
    raw = (response.choices[0].message.content or "").strip()

    # max_tokens에 걸려 응답이 중간에 잘렸으면(finish_reason == "length") 더 큰 한도로 1회 재시도.
    # 재시도도 잘리면 검수 전 원문(고도화 완료본)을 그대로 사용 — 잘린 글을 저장하는 것보다 안전.
    if response.choices[0].finish_reason == "length":
        console.print("[yellow]검수 응답이 토큰 한도에 걸려 잘렸습니다 — 더 큰 한도로 재시도합니다.[/yellow]")
        response = client.chat.completions.create(
            model=REVIEW_MODEL,
            max_completion_tokens=REVIEW_MAX_TOKENS + 4000,
            messages=messages,
        )
        raw = (response.choices[0].message.content or "").strip()
        if response.choices[0].finish_reason == "length":
            console.print("[red]재시도에도 응답이 잘렸습니다 — 검수 전 원문을 그대로 사용합니다.[/red]")
            return ReviewResult(
                score=7,
                feedback="검수 응답이 반복적으로 토큰 한도에 걸려 잘려, 검수 전 원문을 그대로 사용했습니다.",
                final_article=draft,
            )

    return _parse(raw, fallback=draft, known_titles=research.paper_titles)


def _parse(raw: str, fallback: str, known_titles: list[str] | None = None) -> ReviewResult:
    sections: dict[str, list[str]] = {}
    current = None
    for line in raw.splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            current = line[4:-4].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    score_raw = "\n".join(sections.get("SCORE", [])).strip()
    try:
        score = int("".join(c for c in score_raw if c.isdigit())[:2])
        score = max(1, min(10, score))
    except (ValueError, IndexError):
        score = 7

    feedback = "\n".join(sections.get("FEEDBACK", [])).strip()
    final_article = "\n".join(sections.get("FINAL_ARTICLE", [])).strip()

    if len(final_article) < 500:
        final_article = fallback

    citation_warnings = _check_citations(final_article, known_titles or [])
    phrase_warnings = _scan_banned_phrases(final_article)
    if citation_warnings or phrase_warnings:
        console.print("[yellow]─── 코드 레벨 인용 검증 경고 ───[/yellow]")
        for w in citation_warnings:
            console.print(f"[yellow]  출처 불일치: {w}[/yellow]")
        for w in phrase_warnings:
            console.print(f"[yellow]  금지 표현 발견: {w}[/yellow]")
        console.print("[yellow]────────────────────────────[/yellow]")
        warning_block = "\n\n**[코드 레벨 검증 경고 — LLM 검수와 별개로 자동 대조한 결과]**\n" + "\n".join(
            [f"- 출처 불일치: {w}" for w in citation_warnings] + [f"- 금지 표현 발견: {w}" for w in phrase_warnings]
        )
        feedback += warning_block

    return ReviewResult(
        score=score,
        feedback=feedback,
        final_article=final_article,
    )
