#!/usr/bin/env python3
"""
upload_to_tistory.py — 기존 .md 파일을 티스토리에 업로드 (Playwright 브라우저 자동화)

사용:
  python upload_to_tistory.py 파일명.md          # 비공개로 저장
  python upload_to_tistory.py 파일명.md --public  # 공개로 발행
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
from rich.console import Console
from rich.panel import Panel

from tistory_agent import _build_html, _extract_title

load_dotenv()
console = Console(legacy_windows=False, force_terminal=True)


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

        # ── 2. 글쓰기 페이지 이동 ──────────────────────────
        console.print("③ 글쓰기 페이지 이동 중...")
        page.goto(f"https://{blog_name}.tistory.com/manage/post/write")
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

        # ── 4. HTML 편집 모드 전환 ───────────────────────────
        console.print("⑤ HTML 편집 모드 전환 중...")
        page.wait_for_timeout(1000)

        html_btn_clicked = False
        for selector in [
            "button[data-tiara-action-name='HTML']",
            "button.html-editor-btn",
            "button.toolbar-btn[title='HTML']",
            "button:has-text('HTML')",
            "[class*='html'][class*='btn']",
        ]:
            try:
                page.click(selector, timeout=3000)
                html_btn_clicked = True
                break
            except PWTimeout:
                continue

        if not html_btn_clicked:
            console.print("[yellow]  HTML 버튼을 자동으로 찾지 못했습니다. 브라우저에서 직접 HTML 모드로 전환해주세요.[/yellow]")
            input("  HTML 모드로 전환 후 Enter를 누르세요...")

        page.wait_for_timeout(1000)

        # ── 5. HTML 내용 입력 ────────────────────────────────
        console.print("⑥ 내용 입력 중...")

        # CodeMirror 에디터 처리
        cm = page.locator(".CodeMirror")
        if cm.count() > 0:
            cm.click()
            page.keyboard.press("Control+a")
            page.wait_for_timeout(200)
            page.keyboard.type(html)
        else:
            # textarea fallback
            for selector in ["textarea.html-editor", "textarea[name='content']", "#content"]:
                try:
                    page.fill(selector, html, timeout=3000)
                    break
                except PWTimeout:
                    continue

        page.wait_for_timeout(500)

        # ── 6. 발행/저장 ────────────────────────────────────
        console.print("⑦ 저장/발행 중...")

        # 발행 버튼 클릭
        for selector in [
            "#publish-layer-btn",
            "button.btn-publish",
            "button:has-text('발행')",
            "button:has-text('저장')",
        ]:
            try:
                page.click(selector, timeout=3000)
                break
            except PWTimeout:
                continue

        page.wait_for_timeout(2000)

        # 비공개/공개 설정
        if not public:
            for selector in [
                "label[for='visibility-private']",
                "input[value='0'] + label",
                "button:has-text('비공개')",
            ]:
                try:
                    page.click(selector, timeout=2000)
                    break
                except PWTimeout:
                    continue
        else:
            for selector in [
                "label[for='visibility-public']",
                "input[value='3'] + label",
                "button:has-text('공개')",
            ]:
                try:
                    page.click(selector, timeout=2000)
                    break
                except PWTimeout:
                    continue

        # 최종 확인 버튼
        for selector in [
            "button.btn-publish-confirm",
            "button:has-text('확인')",
            "button:has-text('완료')",
        ]:
            try:
                page.click(selector, timeout=3000)
                break
            except PWTimeout:
                continue

        page.wait_for_timeout(2000)
        console.print(Panel(
            f"[green]업로드 완료![/green]\n"
            f"블로그: https://{blog_name}.tistory.com/manage",
            border_style="green",
        ))

        input("브라우저를 닫으려면 Enter를 누르세요...")
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
