import openai

from models import ReviewResult, ResearchOutput
from config import REVIEW_MODEL, REVIEW_MAX_TOKENS, REVIEW_SYSTEM_PROMPT


def run_review_agent(draft: str, research: ResearchOutput) -> ReviewResult:
    client = openai.OpenAI()

    user_prompt = f"""
주제 "{research.topic}", 독자 40-50대 한국 여성을 위한 다음 초안을 검수해줘.

=== 초안 ===
{draft}
""".strip()

    response = client.chat.completions.create(
        model=REVIEW_MODEL,
        max_tokens=REVIEW_MAX_TOKENS,
        messages=[
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = (response.choices[0].message.content or "").strip()
    return _parse(raw, fallback=draft)


def _parse(raw: str, fallback: str) -> ReviewResult:
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

    return ReviewResult(
        score=score,
        feedback=feedback,
        final_article=final_article or fallback,
    )
