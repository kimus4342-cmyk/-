import openai
from rich.console import Console

from models import ReviewInsights
from config import (
    REVIEW_COLLECTOR_MODEL,
    REVIEW_COLLECTOR_MAX_TOKENS,
    REVIEW_COLLECTOR_SYSTEM_PROMPT,
)

console = Console(legacy_windows=False)

_MAX_FIELD_LEN = 200


def run_review_collector(topic: str, skin_concern: str) -> ReviewInsights | None:
    """올리브영·네이버에서 실사용 후기 패턴을 수집한다. 실패 시 None 반환."""
    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model=REVIEW_COLLECTOR_MODEL,
            max_tokens=REVIEW_COLLECTOR_MAX_TOKENS,
            messages=[
                {"role": "system", "content": REVIEW_COLLECTOR_SYSTEM_PROMPT},
                {"role": "user", "content": f"주제: {topic}\n피부 고민: {skin_concern}"},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        return _parse(raw)
    except Exception as e:
        console.print(f"[yellow]후기 수집 실패 — 이 단계를 건너뜁니다. ({e})[/yellow]")
        return None


def _parse(raw: str) -> ReviewInsights | None:
    sections: dict[str, list[str]] = {}
    current = None
    for line in raw.splitlines():
        if line.startswith("=== ") and line.endswith(" ==="):
            current = line[4:-4].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    positive = "\n".join(sections.get("POSITIVE_PATTERNS", [])).strip()
    negative = "\n".join(sections.get("NEGATIVE_PATTERNS", [])).strip()
    mistakes = "\n".join(sections.get("COMMON_MISTAKES", [])).strip()
    sources_raw = "\n".join(sections.get("SOURCES", [])).strip()
    sources = "" if not sources_raw or "없음" in sources_raw else sources_raw

    # 각 필드에서 "데이터 부족" 아닌 실질적 줄이 하나라도 있으면 유효
    def _has_real_content(field: str) -> bool:
        return any(
            "데이터 부족" not in line and len(line.strip()) > 5
            for line in field.splitlines()
            if line.strip()
        )

    meaningful = [f for f in [positive, negative, mistakes] if _has_real_content(f)]
    if not meaningful:
        console.print("[yellow]후기 수집: 유효한 패턴 없음 — 이 단계를 건너뜁니다.[/yellow]")
        return None

    # 필드 길이 제한 (작성 에이전트 토큰 절약)
    if sources:
        console.print(f"[dim]후기 출처 URL 확인됨: {sources[:80]}{'...' if len(sources) > 80 else ''}[/dim]")
    else:
        console.print("[yellow]후기 출처 URL 없음 — 패턴은 참고용으로만 활용됩니다.[/yellow]")

    return ReviewInsights(
        positive_patterns=positive[:_MAX_FIELD_LEN],
        negative_patterns=negative[:_MAX_FIELD_LEN],
        common_mistakes=mistakes[:_MAX_FIELD_LEN],
        sources=sources[:300],
    )
