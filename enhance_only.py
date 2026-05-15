#!/usr/bin/env python3
# enhance_only.py — 마지막 생성 파일에 고도화 에이전트만 단독 실행

import os
import re
import sys
from datetime import datetime

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from models import ResearchOutput, Product
from enhancement_agent import run_enhancement_agent

load_dotenv()
console = Console(legacy_windows=False, force_terminal=True)


def find_latest_article() -> tuple[str, str] | None:
    """가장 최근 생성된 주제명_YYYYMMDD_NNN.md 파일과 주제명 반환."""
    pattern = re.compile(r"^(.+)_(\d{8})_(\d{3})\.md$")
    candidates = []
    for f in os.listdir("."):
        m = pattern.match(f)
        if m:
            candidates.append((m.group(2), m.group(3), f, m.group(1)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, _, filename, topic = candidates[0]
    return filename, topic


def load_article(filename: str) -> str:
    with open(filename, encoding="utf-8") as f:
        content = f.read()
    # 첫 줄 헤더("# BLOOMI 큐레이션 — ...") 제거하고 본문만 반환
    lines = content.splitlines()
    body_start = next((i for i, l in enumerate(lines) if l.startswith("## ") or (l.strip() and not l.startswith("# "))), 0)
    return "\n".join(lines[body_start:]).strip()


def save_enhanced(content: str, topic: str, source_filename: str) -> str:
    safe_name = re.sub(r"[^\w가-힣]", "_", topic)
    date = datetime.now().strftime("%Y%m%d")
    existing = len([f for f in os.listdir(".") if re.match(rf"{re.escape(safe_name)}_{date}_\d{{3}}\.md", f)])
    number = f"{existing + 1:03d}"
    filename = f"{safe_name}_{date}_{number}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# BLOOMI 큐레이션 — {topic} (고도화)\n\n")
        f.write(f"> 원본: `{source_filename}`\n\n")
        f.write(content)
    return filename


def main():
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[bold red]오류:[/bold red] OPENAI_API_KEY가 설정되지 않았습니다.")
        return

    # 파일 지정: python enhance_only.py 파일명.md  또는 자동 탐색
    if len(sys.argv) > 1:
        source_file = sys.argv[1]
        topic = re.sub(r"_\d{8}_\d{3}\.md$", "", source_file).replace("_", " ")
    else:
        result = find_latest_article()
        if not result:
            console.print("[bold red]오류:[/bold red] 현재 디렉터리에 생성된 .md 파일이 없습니다.")
            console.print("  → python enhance_only.py 파일명.md 으로 직접 지정하세요.")
            return
        source_file, topic = result

    if not os.path.exists(source_file):
        console.print(f"[bold red]오류:[/bold red] 파일을 찾을 수 없습니다: {source_file}")
        return

    console.print(Panel(
        f"[bold]대상 파일:[/bold] {source_file}\n"
        f"[bold]주제:[/bold] {topic.replace('_', ' ')}",
        title="[bold green]고도화 에이전트 단독 실행[/bold green]",
        border_style="green",
        padding=(1, 4),
    ))

    article = load_article(source_file)

    # 주제 정보만 담은 최소 ResearchOutput 구성
    research = ResearchOutput(
        topic=topic.replace("_", " "),
        skin_concern="",
        core_message="",
        key_insights="",
        editorial_angle="",
        products=[],
    )

    console.print()
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True, console=console) as p:
        p.add_task("트렌드·SEO·경쟁 분석 및 고도화 중...", total=None)
        enhancement = run_enhancement_agent(article, research)

    console.print(Panel(
        f"[bold]SEO 키워드:[/bold] {enhancement.seo_keywords[:120]}{'...' if len(enhancement.seo_keywords) > 120 else ''}\n\n"
        f"[bold]차별화 포인트:[/bold]\n{enhancement.competitor_gaps[:200]}{'...' if len(enhancement.competitor_gaps) > 200 else ''}\n\n"
        f"[dim]고도화 완료 — {len(enhancement.enhanced_article):,}자[/dim]",
        title="[bold green]고도화 에이전트 완료[/bold green]",
        border_style="green",
    ))

    console.print()
    console.print(Panel(
        Markdown(enhancement.enhanced_article),
        title="[bold green]✦ 고도화 완성본[/bold green]",
        border_style="green",
        padding=(1, 3),
    ))

    out_file = save_enhanced(enhancement.enhanced_article, topic, source_file)
    console.print(f"[green]저장 완료:[/green] {out_file}")


if __name__ == "__main__":
    main()
