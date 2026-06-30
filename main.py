#!/usr/bin/env python3
# main.py — BLOOMI 멀티 에이전트 실행 진입점

import argparse
import os
import re
from datetime import datetime

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from pipeline import run_pipeline
from research_agent import run_topic_proposal

load_dotenv()
console = Console(legacy_windows=False, force_terminal=True)


def save_output(content: str, topic: str) -> str:
    safe_name = re.sub(r"[^\w가-힣]", "_", topic)
    date = datetime.now().strftime("%Y%m%d")
    existing = len([f for f in os.listdir(".") if re.match(rf"{re.escape(safe_name)}_{date}_\d{{3}}\.md", f)])
    number = f"{existing + 1:03d}"
    filename = f"{safe_name}_{date}_{number}.md"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"# BLOOMI 큐레이션 — {topic}\n\n")
        f.write(content)
    return filename


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", type=str, default=None, help="주제를 직접 지정 (주제 선택 단계 건너뜀)")
    parser.add_argument("--topics-only", action="store_true", help="주제 후보만 조회하고 종료")
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        console.print("[bold red]오류:[/bold red] OPENAI_API_KEY가 설정되지 않았습니다.")
        console.print("  → .env 파일에 OPENAI_API_KEY를 입력하세요.")
        return

    console.print(Panel(
        "[bold]BLOOMI[/bold] — 4050 뷰티 큐레이션 멀티 에이전트\n"
        "[dim]주제 선택 → 리서치 → 작성 → 검수 → 고도화[/dim]",
        border_style="dark_orange",
        padding=(1, 4),
    ))

    if args.topics_only:
        from rich.table import Table
        candidates = run_topic_proposal()
        table = Table(show_header=True, header_style="bold cyan", border_style="cyan", padding=(0, 1))
        table.add_column("번호", width=4, justify="center")
        table.add_column("주제", width=26)
        table.add_column("유형", width=12)
        table.add_column("각도", width=12)
        table.add_column("선정 이유", width=38)
        for i, c in enumerate(candidates, 1):
            table.add_row(str(i), c.get("topic", "—"), c.get("type", "—"), c.get("angle", "—"), c.get("reason", "—"))
        console.print()
        from rich.panel import Panel as _Panel
        console.print(_Panel(table, title="[bold cyan]주제 후보[/bold cyan]", border_style="cyan"))
        return

    console.print()
    article, research = run_pipeline(preset_topic=args.topic)

    console.print()
    console.print(Panel(
        Markdown(article),
        title="[bold green]✦ 최종 완성본[/bold green]",
        border_style="green",
        padding=(1, 3),
    ))

    filename = save_output(article, research.topic)
    console.print(f"[green]저장 완료:[/green] {filename}")


if __name__ == "__main__":
    main()
