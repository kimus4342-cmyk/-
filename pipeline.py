from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from models import ResearchOutput
from research_agent import run_topic_proposal, run_research_agent
from writing_agent import run_writing_agent
from review_agent import run_review_agent
from enhancement_agent import run_enhancement_agent

console = Console(legacy_windows=False, force_terminal=True)


def run_pipeline() -> tuple[str, ResearchOutput]:
    # ① 주제 후보 제안
    with _spin("트렌드 탐색 중 — 주제 후보 조사 중..."):
        candidates = run_topic_proposal()

    if not candidates:
        console.print("[red]주제 후보 조회 실패. 기본 주제로 진행합니다.[/red]")
        selected_topic = "피부 장벽 강화"
    else:
        table = Table(show_header=True, header_style="bold cyan", border_style="cyan", padding=(0, 1))
        table.add_column("번호", width=4, justify="center")
        table.add_column("주제", width=20)
        table.add_column("각도", width=12)
        table.add_column("선정 이유", width=50)

        for i, c in enumerate(candidates, 1):
            table.add_row(
                str(i),
                c.get("topic", "—"),
                c.get("angle", "—"),
                c.get("reason", "—"),
            )

        console.print()
        console.print(Panel(table, title="[bold cyan]① 주제 후보[/bold cyan]", border_style="cyan"))
        console.print()

        selected_topic = _ask_selection(candidates)

    console.print(Panel(
        f"[bold]선택된 주제:[/bold] {selected_topic}",
        title="[bold cyan]주제 확정[/bold cyan]",
        border_style="cyan",
    ))

    # ② 리서치 에이전트
    with _spin(f"'{selected_topic}' 논문·제품 리서치 중..."):
        research = run_research_agent(selected_topic)

    console.print(Panel(
        f"[bold]선정 주제:[/bold] {research.topic}\n"
        f"[bold]피부 고민:[/bold] {research.skin_concern}\n"
        f"[bold]추천 제품:[/bold] {', '.join(p.name for p in research.products)}",
        title="[bold cyan]② 리서치 에이전트 완료[/bold cyan]",
        border_style="cyan",
    ))

    # ③ 작성 에이전트
    with _spin("콘텐츠 초안 작성 중..."):
        draft = run_writing_agent(research)

    console.print(Panel(
        f"[dim]초안 생성 완료 — {len(draft):,}자[/dim]",
        title="[bold yellow]③ 작성 에이전트 완료[/bold yellow]",
        border_style="yellow",
    ))

    # ④ 검수 에이전트
    with _spin("가독성·흥미도 검수 중..."):
        review = run_review_agent(draft, research)

    verdict = "[green]승인[/green]" if review.score >= 8 else "[red]직접 수정 완료[/red]"
    short_feedback = review.feedback[:200] + ("..." if len(review.feedback) > 200 else "")
    console.print(Panel(
        f"[bold]검수 점수:[/bold] {review.score}/10  {verdict}\n\n"
        f"[bold]피드백:[/bold]\n{short_feedback}",
        title="[bold magenta]④ 검수 에이전트 완료[/bold magenta]",
        border_style="magenta",
    ))

    # ⑤ 고도화 에이전트
    with _spin("트렌드·SEO·경쟁 분석 및 고도화 중..."):
        enhancement = run_enhancement_agent(review.final_article, research)

    console.print(Panel(
        f"[bold]SEO 키워드:[/bold] {enhancement.seo_keywords[:120]}{'...' if len(enhancement.seo_keywords) > 120 else ''}\n\n"
        f"[bold]차별화 포인트:[/bold]\n{enhancement.competitor_gaps[:200]}{'...' if len(enhancement.competitor_gaps) > 200 else ''}\n\n"
        f"[dim]고도화 완료 — {len(enhancement.enhanced_article):,}자[/dim]",
        title="[bold green]⑤ 고도화 에이전트 완료[/bold green]",
        border_style="green",
    ))

    return enhancement.enhanced_article, research


def _ask_selection(candidates: list[dict]) -> str:
    valid = {str(i) for i in range(1, len(candidates) + 1)}
    while True:
        try:
            choice = console.input(f"[bold]주제를 선택하세요 (1~{len(candidates)}): [/bold]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]입력 없음 — 1번으로 진행합니다.[/yellow]")
            choice = "1"

        if choice in valid:
            return candidates[int(choice) - 1].get("topic", "미분류 주제")
        console.print(f"[red]1~{len(candidates)} 중 하나를 입력하세요.[/red]")


@contextmanager
def _spin(msg: str):
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True, console=console) as p:
        p.add_task(msg, total=None)
        yield
