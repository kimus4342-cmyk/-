#!/usr/bin/env python3
"""
upload_to_tistory.py — 기존 .md 파일을 티스토리에 업로드 (Playwright 브라우저 자동화)

사용:
  python upload_to_tistory.py 파일명.md          # 비공개로 저장
  python upload_to_tistory.py 파일명.md --public  # 공개로 발행
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from rich.console import Console
from rich.panel import Panel

from tistory_agent import _build_html, _extract_title

load_dotenv()
console = Console(legacy_windows=False, force_terminal=True)


def _captcha_present(page) -> bool:
    """DKAPTCHA 위젯은 iframe 안에 렌더링되므로 모든 frame을 뒤져서 확인한다."""
    for frame in page.frames:
        try:
            if frame.get_by_text("DKAPTCHA").count() > 0:
                return True
        except Exception:
            continue
    return False


def upload(md_path: str, public: bool = False) -> None:
    email = os.getenv("TISTORY_EMAIL", "")
    password = os.getenv("TISTORY_PASSWORD", "")
    blog_name = os.getenv("TISTORY_BLOG_NAME", "")

    if not all([email, password, blog_name]):
        console.print("[red]오류: .env에 TISTORY_EMAIL, TISTORY_PASSWORD, TISTORY_BLOG_NAME 를 모두 입력하세요.[/red]")
        sys.exit(1)

    content = Path(md_path).read_text(encoding="utf-8")
    title = _extract_title(content)
    html = _build_html(content)

    console.print(Panel(
        f"[bold]제목:[/bold] {title}\n"
        f"[bold]파일:[/bold] {md_path}\n"
        f"[bold]공개:[/bold] {'공개' if public else '비공개'}\n"
        f"[bold]블로그:[/bold] {blog_name}.tistory.com",
        title="[bold cyan]티스토리 업로드 시작[/bold cyan]",
        border_style="cyan",
    ))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=300)
        page = browser.new_page()

        # ── 1. 카카오 로그인 ──────────────────────────────
        console.print("① 로그인 페이지 열기...")
        page.goto("https://www.tistory.com/auth/login")
        page.wait_for_load_state("networkidle")

        # 카카오 로그인 버튼 클릭 (여러 선택자 시도)
        for selector in [
            "a.btn_login.link_kakao_id",
            "a[href*='kakao'][class*='login']",
            "a[class*='kakao']",
        ]:
            try:
                page.click(selector, timeout=3000)
                break
            except PWTimeout:
                continue

        page.wait_for_load_state("networkidle")

        # 카카오 이메일/비밀번호 입력
        console.print("② 카카오 계정 입력 중...")
        try:
            page.fill("#loginId--1", email, timeout=5000)
            page.fill("#password--2", password, timeout=3000)
        except PWTimeout:
            # 구버전 선택자 시도
            page.fill("#loginId", email, timeout=5000)
            page.fill("#loginPw", password, timeout=3000)

        # 로그인 버튼 클릭
        for selector in [
            "button.btn_g.highlight.submit",
            "button[type='submit']",
            ".btn_confirm",
        ]:
            try:
                page.click(selector, timeout=3000)
                break
            except PWTimeout:
                continue

        # 로그인 완료 대기 — URL이 tistory.com 으로 돌아올 때까지 (최대 90초)
        console.print("[yellow]  로그인 완료를 기다리는 중... (최대 90초)[/yellow]")
        try:
            page.wait_for_function(
                "() => location.hostname.includes('tistory.com')",
                timeout=90_000,
            )
        except PWTimeout:
            console.print("[yellow]  자동 감지 실패 — 로그인이 완료됐으면 Enter를 눌러 계속 진행하세요.[/yellow]")
            input("  Enter 키 입력: ")

        page.wait_for_load_state("networkidle")
        console.print("[green]  ✓ 로그인 완료[/green]")

        # ── 2. 관리 페이지 → 새 글 쓰기 버튼 클릭 ─────────
        console.print("③ 관리 페이지 이동 중...")
        page.goto(f"https://{blog_name}.tistory.com/manage")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        console.print("④ 새 글 쓰기 버튼 클릭 중...")
        write_btn_clicked = False
        for selector in [
            "a[href*='post/write']",
            "a:has-text('새 글')",
            "a:has-text('글쓰기')",
            "button:has-text('새 글')",
            ".btn-write",
        ]:
            try:
                page.click(selector, timeout=3000)
                write_btn_clicked = True
                break
            except PWTimeout:
                continue

        if not write_btn_clicked:
            console.print("[yellow]  새 글 쓰기 버튼을 못 찾았습니다. 직접 클릭해주세요.[/yellow]")
            input("  글쓰기 페이지 열린 후 Enter를 누르세요: ")

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # ── 3. 제목 입력 ────────────────────────────────────
        console.print("④ 제목 입력 중...")
        for selector in ["#post-title-inp", "input[name='title']", ".title-input"]:
            try:
                page.fill(selector, title, timeout=3000)
                break
            except PWTimeout:
                continue

        # ── 4. TinyMCE 완전 초기화 대기 후 주입 ─────────────
        console.print("⑤ 내용 주입 중...")
        try:
            page.wait_for_function(
                "() => { const ed = tinymce.get('editor-tistory'); return ed && ed.initialized; }",
                timeout=15_000,
            )
        except PWTimeout:
            page.wait_for_timeout(3000)

        # setContent + 이벤트 트리거
        page.evaluate(f"""() => {{
            const h = {json.dumps(html)};
            const ed = tinymce.get('editor-tistory');
            if (ed) {{
                ed.setContent(h);
                ed.undoManager.clear();
                ed.undoManager.add();
                ed.fire('change');
                ed.fire('input');
            }}
        }}""")
        page.wait_for_timeout(1000)

        # 주입 결과 확인
        content_len = page.evaluate("""() => {
            const ed = tinymce.get('editor-tistory');
            return ed ? ed.getContent().length : 0;
        }""")
        console.print(f"[dim]  주입 후 내용 길이: {content_len}자[/dim]")

        if content_len < 100:
            console.print("[yellow]  내용이 비어 있습니다. 브라우저에서 직접 확인 후 Enter를 눌러주세요.[/yellow]")
            input("  Enter 키: ")

        page.wait_for_timeout(500)

        # ── 6. 발행/저장 ────────────────────────────────────
        console.print("⑦ 저장/발행 중...")

        # "완료" 버튼 클릭 → 발행 설정 모달 열기 (모달 기본 공개범위는 비공개)
        for selector in ["#publish-layer-btn", "button.btn-publish", "button:has-text('완료')"]:
            try:
                page.click(selector, timeout=3000)
                break
            except PWTimeout:
                continue

        page.wait_for_timeout(1500)

        # 공개로 발행할 경우에만 "공개" 라디오를 선택 (기본값이 비공개이므로 비공개는 그대로 둠)
        if public:
            try:
                page.get_by_text("공개", exact=True).click(timeout=2000)
            except PWTimeout:
                pass
            page.wait_for_timeout(500)

        # 최종 저장 버튼 — 선택된 공개범위에 따라 "발행"/"비공개 저장"/"보호 저장" 등으로 텍스트가 바뀜
        confirmed = False
        for name in ["발행", "비공개 저장", "보호 저장", "공개 저장", "저장"]:
            try:
                page.get_by_role("button", name=name, exact=True).click(timeout=2000)
                confirmed = True
                break
            except PWTimeout:
                continue

        page.wait_for_timeout(1000)

        # 자동입력 방지(CAPTCHA)가 뜰 수 있음 — DKAPTCHA는 iframe 안에서 렌더링되므로
        # 모든 frame을 대상으로 능동 폴링한다
        captcha_shown = False
        deadline = time.time() + 5
        while time.time() < deadline:
            if _captcha_present(page):
                captcha_shown = True
                break
            page.wait_for_timeout(300)

        if captcha_shown:
            console.print(Panel(
                "[yellow]자동입력 방지(CAPTCHA)가 떴습니다.[/yellow]\n"
                "브라우저 창에서 직접 답을 입력하고 [bold]답변 제출[/bold]을 눌러주세요.\n"
                "[dim]완료되면 자동으로 이어서 진행됩니다 (최대 5분 대기)[/dim]",
                title="[bold yellow]⚠ 사람 확인 필요[/bold yellow]",
                border_style="yellow",
            ))
            solved = False
            deadline = time.time() + 300
            while time.time() < deadline:
                if not _captcha_present(page):
                    solved = True
                    break
                page.wait_for_timeout(1000)
            if solved:
                console.print("[green]  ✓ CAPTCHA 통과 확인[/green]")
                page.wait_for_timeout(2000)
            else:
                console.print("[yellow]  자동 감지 실패 — CAPTCHA를 푸셨으면 Enter를 눌러 계속하세요.[/yellow]")
                try:
                    input("  Enter 키: ")
                except EOFError:
                    pass

        # 저장 완료 여부 확인 — 글쓰기 화면(newpost)을 벗어났는지로 판단
        saved = "newpost" not in page.url

        if confirmed and saved:
            console.print(Panel(
                f"[green]업로드 완료![/green]\n"
                f"블로그: https://{blog_name}.tistory.com/manage",
                border_style="green",
            ))
        elif confirmed and not saved:
            console.print(Panel(
                "[yellow]저장 버튼은 눌렀지만 아직 글쓰기 화면에 남아있습니다.\n"
                "브라우저 창에서 정상적으로 저장됐는지 직접 확인해주세요.[/yellow]",
                border_style="yellow",
            ))
        else:
            console.print(Panel(
                "[red]발행 확인 버튼을 찾지 못했습니다. 브라우저 창에서 직접 확인 후 저장해주세요.[/red]",
                border_style="red",
            ))

        try:
            input("브라우저를 닫으려면 Enter를 누르세요...")
        except EOFError:
            pass
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="마크다운 파일을 티스토리에 업로드합니다.")
    parser.add_argument("file", help="업로드할 .md 파일 경로")
    parser.add_argument("--public", action="store_true", help="공개로 발행 (기본: 비공개)")
    args = parser.parse_args()

    if not Path(args.file).exists():
        console.print(f"[red]파일을 찾을 수 없습니다: {args.file}[/red]")
        sys.exit(1)

    upload(args.file, public=args.public)
