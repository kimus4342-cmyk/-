from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from models import ResearchOutput
from research_agent import run_research_agent
from writing_agent import run_writing_agent
from review_agent import run_review_agent

console = Console(legacy_windows=False, force_terminal=True)


def run_pipeline() -> tuple[str, ResearchOutput]:
    # ① 리서치 에이전트
    with _spin("트렌드 주제 탐색 및 논문 검색 중..."):
        research = run_research_agent()

    console.print(Panel(
        f"[bold]선정 주제:[/bold] {research.topic}\n"
        f"[bold]피부 고민:[/bold] {research.skin_concern}\n"
        f"[bold]추천 제품:[/bold] {', '.join(p.name for p in research.products)}",
        title="[bold cyan]① 리서치 에이전트 완료[/bold cyan]",
        border_style="cyan",
    ))

    # ② 작성 에이전트
    with _spin("콘텐츠 초안 작성 중..."):
        draft = run_writing_agent(research)

    console.print(Panel(
        f"[dim]초안 생성 완료 — {len(draft):,}자[/dim]",
        title="[bold yellow]② 작성 에이전트 완료[/bold yellow]",
        border_style="yellow",
    ))

    # ③ 검수 에이전트
    with _spin("가독성·흥미도 검수 중..."):
        review = run_review_agent(draft, research)

    verdict = "[green]승인[/green]" if review.score >= 8 else "[red]직접 수정 완료[/red]"
    short_feedback = review.feedback[:200] + ("..." if len(review.feedback) > 200 else "")
    console.print(Panel(
        f"[bold]검수 점수:[/bold] {review.score}/10  {verdict}\n\n"
        f"[bold]피드백:[/bold]\n{short_feedback}",
        title="[bold magenta]③ 검수 에이전트 완료[/bold magenta]",
        border_style="magenta",
    ))

    return review.final_article, research


@contextmanager
def _spin(msg: str):
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True, console=console) as p:
        p.add_task(msg, total=None)
        yield
