"""
tistory_agent.py — 티스토리 자동 등록 에이전트
완성 글(마크다운)을 디자인된 HTML로 변환해 티스토리에 포스팅합니다.
"""

import os
import re

import requests
from markdown import markdown
from rich.console import Console
from rich.panel import Panel

console = Console(legacy_windows=False, force_terminal=True)

_API = "https://www.tistory.com/apis"

# ──────────────────────────────────────────────
#  디자인 — 4050 뷰티 큐레이션 테마
# ──────────────────────────────────────────────
_STYLE = """\
<style>
.bloomi{max-width:700px;margin:0 auto;font-family:'Apple SD Gothic Neo','나눔고딕',sans-serif;
  font-size:16px;line-height:1.9;color:#2d2d2d;word-break:keep-all;-webkit-font-smoothing:antialiased}
.bloomi h1{font-size:22px;font-weight:700;color:#1a1a1a;margin:28px 0 14px;line-height:1.4}
.bloomi h2{font-size:19px;font-weight:700;color:#1a1a1a;margin:36px 0 14px;
  padding:11px 16px;background:#fff2f0;border-left:5px solid #d96b6b;border-radius:0 8px 8px 0}
.bloomi h3{font-size:17px;font-weight:600;color:#222;margin:28px 0 12px;
  padding-bottom:7px;border-bottom:2px solid #f5d5d5}
.bloomi h4{font-size:16px;font-weight:600;color:#333;margin:22px 0 10px;
  padding-left:11px;border-left:3px solid #d96b6b}
.bloomi p{margin:13px 0}
.bloomi ul{list-style:none;padding:0;margin:12px 0}
.bloomi li{position:relative;padding-left:18px;margin:7px 0}
.bloomi li::before{content:"·";color:#d96b6b;position:absolute;left:5px;
  font-size:22px;line-height:1.25;font-weight:700}
.bloomi strong{color:#b84444;font-weight:600}
.bloomi em{font-style:normal;background:#fff5e0;padding:1px 4px;border-radius:3px}
.bloomi blockquote{background:#fff8f5;border-left:4px solid #e8a080;padding:13px 17px;
  margin:16px 0;border-radius:0 8px 8px 0;color:#555;font-size:15px}
.bloomi hr{border:none;border-top:1px solid #f0e0e0;margin:28px 0}
.bloomi table{width:100%;border-collapse:collapse;margin:14px 0;font-size:14px}
.bloomi th{background:#f9e8e8;padding:10px 13px;text-align:left;
  border:1px solid #e8d0d0;font-weight:600;color:#333}
.bloomi td{padding:9px 13px;border:1px solid #edd8d8;vertical-align:top}
.bloomi tr:nth-child(even) td{background:#fdf5f5}
/* 핵심 요약 박스 — 글 첫 번째 ul에 자동 적용 */
.bloomi-summary{background:linear-gradient(135deg,#fff8f8,#fff0ee);
  border:1px solid #f0c8c8;border-radius:12px;padding:18px 22px;margin:18px 0 28px}
.bloomi-summary li{padding-left:24px;margin:6px 0}
.bloomi-summary li::before{content:"✓";font-size:15px;left:0;line-height:1.75;font-weight:700}
@media(max-width:640px){
  .bloomi{font-size:15px}
  .bloomi h1{font-size:20px}
  .bloomi h2{font-size:17px;padding:9px 13px}
  .bloomi h3{font-size:16px}
}
</style>"""


def setup_tistory_auth() -> None:
    """티스토리 OAuth 최초 인증 — access_token 발급 안내."""
    client_id = os.getenv("TISTORY_CLIENT_ID", "")
    client_secret = os.getenv("TISTORY_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        console.print(Panel(
            "[red]TISTORY_CLIENT_ID / TISTORY_CLIENT_SECRET 이 .env에 없습니다.[/red]\n\n"
            "티스토리 개발자 센터에서 앱을 먼저 등록하세요:\n"
            "[cyan]https://www.tistory.com/guide/api/manage/register[/cyan]\n\n"
            "CallbackURL은 [bold]https://www.tistory.com/oauth[/bold] 로 설정 후\n"
            ".env에 아래 두 값을 추가하세요:\n"
            "  TISTORY_CLIENT_ID=...\n"
            "  TISTORY_CLIENT_SECRET=...",
            title="[bold red]티스토리 앱 등록 필요[/bold red]",
            border_style="red",
        ))
        return

    auth_url = (
        "https://www.tistory.com/oauth/authorize"
        f"?client_id={client_id}"
        "&redirect_uri=https://www.tistory.com/oauth"
        "&response_type=code"
    )

    console.print(Panel(
        "[bold]1.[/bold] 아래 URL을 브라우저에서 여세요:\n\n"
        f"  [cyan]{auth_url}[/cyan]\n\n"
        "[bold]2.[/bold] 티스토리 로그인 → 허가 클릭\n\n"
        "[bold]3.[/bold] 리다이렉트된 URL에서 [bold]code=[/bold] 뒤 값을 복사하세요\n"
        "  예) https://www.tistory.com/oauth?code=[bold]ABC123...[/bold]",
        title="[bold cyan]티스토리 OAuth 인증[/bold cyan]",
        border_style="cyan",
    ))

    code = input("  code 값 붙여넣기: ").strip()
    if not code:
        console.print("[red]code가 없습니다. 취소됩니다.[/red]")
        return

    resp = requests.get(
        "https://www.tistory.com/oauth/access_token",
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": "https://www.tistory.com/oauth",
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )

    from urllib.parse import parse_qs
    parsed = parse_qs(resp.text)
    token = parsed.get("access_token", [""])[0]

    if token:
        console.print(Panel(
            "[green]인증 성공![/green]\n\n"
            ".env 파일에 아래를 추가하세요:\n\n"
            f"  [bold]TISTORY_ACCESS_TOKEN={token}[/bold]\n"
            "  [bold]TISTORY_BLOG_NAME=내블로그이름[/bold]  ← 티스토리 주소의 subdomain\n"
            "  [bold]TISTORY_CATEGORY_ID=0[/bold]          ← 0=기본, 숫자=특정 카테고리\n"
            "  [bold]TISTORY_VISIBILITY=0[/bold]            ← 0=비공개, 3=공개",
            title="[bold green]인증 완료[/bold green]",
            border_style="green",
        ))
    else:
        console.print(f"[red]인증 실패:[/red] {resp.text[:300]}")


def post_to_tistory(
    article: str,
    seo_keywords: str = "",
    visibility: str | None = None,
) -> str | None:
    """
    완성 글(마크다운)을 티스토리에 등록합니다.

    Args:
        article: 마크다운 글 전문
        seo_keywords: 고도화 에이전트가 생성한 SEO 키워드 (태그로 변환)
        visibility: "0"=비공개(기본), "3"=공개

    Returns:
        등록된 포스트 URL, 실패 시 None
    """
    access_token = os.getenv("TISTORY_ACCESS_TOKEN", "")
    blog_name = os.getenv("TISTORY_BLOG_NAME", "")
    category_id = os.getenv("TISTORY_CATEGORY_ID", "0")

    if not access_token or not blog_name:
        console.print(
            "[yellow]⚠ 티스토리 설정 없음 — .env에 TISTORY_ACCESS_TOKEN, "
            "TISTORY_BLOG_NAME 를 추가하고 다시 실행하세요.[/yellow]\n"
            "  처음 설정이라면: [bold]python main.py --setup-tistory[/bold]"
        )
        return None

    if visibility is None:
        visibility = os.getenv("TISTORY_VISIBILITY", "0")

    title = _extract_title(article)
    html_content = _build_html(article)
    tags = _extract_tags(seo_keywords)

    resp = requests.post(
        f"{_API}/post/write",
        params={
            "access_token": access_token,
            "output": "json",
            "blogName": blog_name,
            "title": title,
            "content": html_content,
            "visibility": visibility,
            "category": category_id,
            "tag": tags,
            "acceptComment": "1",
        },
        timeout=15,
    )

    if resp.status_code == 200:
        data = resp.json().get("tistory", {})
        if str(data.get("status")) == "200":
            return data.get("url", "")

    console.print(f"[red]티스토리 등록 실패 ({resp.status_code}):[/red] {resp.text[:200]}")
    return None


# ──────────────────────────────────────────────
#  내부 헬퍼
# ──────────────────────────────────────────────

def _extract_title(article: str) -> str:
    """마크다운 첫 H1/H2 제목을 추출합니다."""
    for line in article.splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return "BLOOMI 큐레이션"


def _build_html(article: str) -> str:
    """마크다운 → 스타일된 HTML 변환."""
    # 첫 번째 H1은 Tistory 포스트 제목과 중복되므로 제거
    lines = article.splitlines()
    cleaned_lines = []
    first_h1_removed = False
    for line in lines:
        if not first_h1_removed and re.match(r"^#\s+", line):
            first_h1_removed = True
            continue
        cleaned_lines.append(line)
    md_text = "\n".join(cleaned_lines)

    # 마크다운 → HTML
    html = markdown(md_text, extensions=["tables", "extra", "nl2br"])

    # 첫 번째 <ul>을 핵심 요약 박스로 변환
    html = _apply_summary_box(html)

    return f"{_STYLE}\n<div class=\"bloomi\">\n{html}\n</div>"


def _apply_summary_box(html: str) -> str:
    """글의 첫 번째 <ul>을 핵심 요약 박스로 래핑합니다."""
    match = re.search(r"<ul>(.*?)</ul>", html, re.DOTALL | re.IGNORECASE)
    if match:
        original = match.group(0)
        wrapped = f'<div class="bloomi-summary">{original}</div>'
        html = html.replace(original, wrapped, 1)
    return html


def _extract_tags(seo_keywords: str) -> str:
    """SEO 키워드 → 티스토리 태그 문자열 (최대 10개, 쉼표 구분)."""
    cleaned = re.sub(r"[#\n]", " ", seo_keywords)
    parts = [t.strip() for t in re.split(r"[,\s]+", cleaned) if t.strip()]
    return ",".join(parts[:10])
