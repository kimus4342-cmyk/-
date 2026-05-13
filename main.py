#!/usr/bin/env python3
# main.py — BLOOMI 멀티 에이전트 실행 진입점

import os
import re
from datetime import datetime

from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from pipeline import run_pipeline

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
    if not os.getenv("OPENAI_API_KEY"):
        console.print("[bold red]오류:[/bold red] OPENAI_API_KEY가 설정되지 않았습니다.")
        console.print("  → .env 파일에 OPENAI_API_KEY를 입력하세요.")
        return

    console.print(Panel(
        "[bold]BLOOMI[/bold] — 4050 뷰티 큐레이션 멀티 에이전트\n"
        "[dim]리서치 에이전트 → 작성 에이전트 → 검수 에이전트[/dim]",
        border_style="dark_orange",
        padding=(1, 4),
    ))

    console.print()
    article, research = run_pipeline()

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
