from contextlib import contextmanager

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from models import ResearchOutput
from research_agent import run_topic_proposal, run_topic_refinement, run_research_agent
from review_collector_agent import run_review_collector
from writing_agent import run_writing_agent, replace_products_in_article
from product_search_agent import run_product_search_agent
from review_agent import run_review_agent
from enhancement_agent import run_enhancement_agent
from tistory_agent import post_to_tistory

console = Console(legacy_windows=False, force_terminal=True)


def run_pipeline(
    preset_topic: str | None = None,
    auto_post: bool = False,
    post_visibility: str = "0",
) -> tuple[str, ResearchOutput]:
    selected_keyword = ""
    if preset_topic:
        selected_topic = preset_topic
        console.print(Panel(
            f"[bold]지정 주제:[/bold] {preset_topic}",
            title="[bold cyan]① 주제 확정 (직접 지정)[/bold cyan]",
            border_style="cyan",
        ))
    else:
        # ① 주제 후보 제안
        with _spin("트렌드 탐색 중 — 주제 후보 조사 중..."):
            candidates = run_topic_proposal()

        if not candidates:
            console.print("[red]주제 후보 조회 실패. 기본 주제로 진행합니다.[/red]")
            selected_topic = "피부 장벽 강화"
        else:
            table = Table(show_header=True, header_style="bold cyan", border_style="cyan", padding=(0, 1))
            table.add_column("번호", width=4, justify="center")
            table.add_column("주제", width=18)
            table.add_column("유형", width=10)
            table.add_column("각도", width=10)
            table.add_column("네이버 상승지수", width=12, justify="center")
            table.add_column("선정 이유", width=44)

            for i, c in enumerate(candidates, 1):
                naver_score = c.get("naver_score")
                table.add_row(
                    str(i),
                    c.get("topic", "—"),
                    c.get("type", "—"),
                    c.get("angle", "—"),
                    f"{naver_score}" if naver_score is not None else "—",
                    c.get("reason", "—"),
                )

            console.print()
            console.print(Panel(table, title="[bold cyan]① 주제 후보[/bold cyan]", border_style="cyan"))
            console.print()

            chosen = _ask_selection(candidates)
            selected_topic = chosen.get("topic", "미분류 주제")
            selected_keyword = chosen.get("keyword", "")

    console.print(Panel(
        f"[bold]선택된 주제:[/bold] {selected_topic}",
        title="[bold cyan]주제 확정[/bold cyan]",
        border_style="cyan",
    ))

    # ①.5 주제 각도화
    with _spin(f"'{selected_topic}' 경쟁 콘텐츠 분석 및 주제 심화 중..."):
        refined_topic = run_topic_refinement(selected_topic)

    if refined_topic != selected_topic:
        console.print(Panel(
            f"[dim]원래 주제:[/dim] {selected_topic}\n"
            f"[bold]심화 주제:[/bold] {refined_topic}",
            title="[bold cyan]① 주제 각도화[/bold cyan]",
            border_style="cyan",
        ))

    # ② 리서치 에이전트
    with _spin(f"'{refined_topic}' 논문·제품 리서치 중..."):
        research = run_research_agent(refined_topic)
    research.keyword = selected_keyword

    product_summary = ', '.join(p.name for p in research.products) if research.products else "[red]제품 없음 — 작성 단계에서 기준만 제시됩니다[/red]"
    console.print(Panel(
        f"[bold]선정 주제:[/bold] {research.topic}\n"
        f"[bold]피부 고민:[/bold] {research.skin_concern}\n"
        f"[bold]추천 제품:[/bold] {product_summary}",
        title="[bold cyan]② 리서치 에이전트 완료[/bold cyan]",
        border_style="cyan",
    ))
    if not research.products:
        console.print("[yellow]경고: 실제 제품을 찾지 못했습니다. 리서치를 다시 실행하거나 주제를 변경하는 것을 권장합니다.[/yellow]")

    # 근거 품질 검사 — 빈약하면 auto_post 차단
    insights_weak = _is_insights_weak(research.key_insights)
    if insights_weak:
        console.print(Panel(
            "[yellow]논문·임상 근거가 충분히 확보되지 않았습니다.[/yellow]\n"
            "글 작성과 저장은 계속 진행하지만 [bold red]자동 게시는 차단[/bold red]됩니다.\n"
            "[dim]생성된 글을 직접 검수한 뒤 수동으로 게시하세요.[/dim]",
            title="[bold yellow]⚠ 근거 품질 경고[/bold yellow]",
            border_style="yellow",
        ))

    # ②.5 후기 수집 에이전트 (실패해도 파이프라인 계속)
    # selected_topic(사용자 선택 원본)은 짧고 검색에 적합 — refined/research.topic은 긴 제목이라 부적합
    with _spin(f"'{selected_topic}' 실사용 후기 패턴 수집 중..."):
        review_insights = run_review_collector(selected_topic, research.skin_concern)

    if review_insights:
        pos_preview = review_insights.positive_patterns[:60] + ("..." if len(review_insights.positive_patterns) > 60 else "")
        neg_preview = review_insights.negative_patterns[:60] + ("..." if len(review_insights.negative_patterns) > 60 else "")
        src_line = (
            f"\n[dim]출처 URL: {review_insights.sources[:80]}[/dim]"
            if review_insights.sources
            else "\n[yellow]출처 URL 없음 — 패턴 신뢰도 낮을 수 있음[/yellow]"
        )
        console.print(Panel(
            f"[bold]긍정 패턴:[/bold] {pos_preview}\n"
            f"[bold]부정 패턴:[/bold] {neg_preview}"
            f"{src_line}",
            title="[bold cyan]②.5 후기 수집 완료[/bold cyan]",
            border_style="cyan",
        ))
    else:
        console.print("[dim]②.5 후기 수집 건너뜀 — 이후 단계는 정상 진행됩니다.[/dim]")

    # ③ 작성 에이전트
    with _spin("콘텐츠 초안 작성 중..."):
        draft = run_writing_agent(research, review_insights)

    console.print(Panel(
        f"[dim]초안 생성 완료 — {len(draft):,}자[/dim]",
        title="[bold yellow]③ 작성 에이전트 완료[/bold yellow]",
        border_style="yellow",
    ))

    # ③.5 제품 재검색 에이전트
    with _spin("글 내용 기반 제품 재검색 중..."):
        updated_products = run_product_search_agent(draft, research)
    if updated_products:
        draft = replace_products_in_article(draft, updated_products)
        console.print(Panel(
            f"[dim]제품 {len(updated_products)}개 교체 완료[/dim]",
            title="[bold yellow]③.5 제품 재검색 완료[/bold yellow]",
            border_style="yellow",
        ))
    else:
        console.print("[dim]③.5 제품 재검색 — 새 제품 없음, 기존 유지[/dim]")

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

    # ⑥ 티스토리 자동 등록 (옵션)
    if auto_post and insights_weak:
        console.print(Panel(
            "[red]근거 품질 미달로 자동 게시를 건너뜁니다.[/red]\n"
            "[dim]글은 로컬에 저장되었습니다. 내용을 직접 확인 후 수동으로 게시하세요.[/dim]",
            title="[bold red]⑥ 자동 게시 차단[/bold red]",
            border_style="red",
        ))
    elif auto_post:
        with _spin("티스토리에 등록 중..."):
            post_url = post_to_tistory(
                enhancement.enhanced_article,
                seo_keywords=enhancement.seo_keywords,
                visibility=post_visibility,
            )

        visibility_label = "[dim]비공개[/dim]" if post_visibility == "0" else "[green]공개[/green]"
        if post_url:
            console.print(Panel(
                f"[bold]URL:[/bold] {post_url}\n"
                f"[bold]공개 여부:[/bold] {visibility_label}",
                title="[bold green]⑥ 티스토리 등록 완료[/bold green]",
                border_style="green",
            ))
        else:
            console.print(Panel(
                "[red]등록에 실패했습니다.[/red]\n"
                "[dim]--setup-tistory 로 인증을 먼저 완료하거나\n"
                ".env의 TISTORY_* 값을 확인하세요.[/dim]",
                title="[bold red]⑥ 티스토리 등록 실패[/bold red]",
                border_style="red",
            ))

    return enhancement.enhanced_article, research


def _is_insights_weak(key_insights: str) -> bool:
    """key_insights가 빈약하면 True 반환.
    판단 기준: 200자 미만이거나 논문 없음 표시가 있으면 빈약으로 간주."""
    if not key_insights or len(key_insights) < 80:
        return True
    weak_markers = [
        "제공된 논문 없음",
        "제공된 PubMed 논문 없음",
        "논문 없음",
        "기전 설명 위주",
    ]
    return any(marker in key_insights for marker in weak_markers)


def _ask_selection(candidates: list[dict]) -> dict:
    valid = {str(i) for i in range(1, len(candidates) + 1)}
    while True:
        try:
            choice = console.input(f"[bold]주제를 선택하세요 (1~{len(candidates)}): [/bold]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]입력 없음 — 1번으로 진행합니다.[/yellow]")
            choice = "1"

        if choice in valid:
            return candidates[int(choice) - 1]
        console.print(f"[red]1~{len(candidates)} 중 하나를 입력하세요.[/red]")


@contextmanager
def _spin(msg: str):
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True, console=console) as p:
        p.add_task(msg, total=None)
        yield
