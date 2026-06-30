import os
import re

import requests
from markdown import markdown
from rich.console import Console
from rich.panel import Panel

console = Console(legacy_windows=False, force_terminal=True)

_TISTORY_API = "https://www.tistory.com/apis"
_REDIRECT_URI = "https://www.tistory.com/oauth"


def setup_tistory_auth() -> None:
    """티스토리 OAuth 최초 인증 — access token 발급 안내."""
    client_id = os.getenv("TISTORY_CLIENT_ID", "")
    client_secret = os.getenv("TISTORY_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        console.print(
            "[red]TISTORY_CLIENT_ID / TISTORY_CLIENT_SECRET 이 .env에 없습니다.[/red]\n"
            "티스토리 개발자 센터(https://www.tistory.com/guide/api/manage/register)에서\n"
            "앱을 등록하고 Client ID와 Secret을 .env에 추가하세요."
        )
        return

    auth_url = (
        f"https://www.tistory.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={_REDIRECT_URI}"
        f"&response_type=code"
    )

    console.print(Panel(
        f"[bold]1.[/bold] 아래 URL을 브라우저에서 여세요:\n\n"
        f"[cyan]{auth_url}[/cyan]\n\n"
        f"[bold]2.[/bold] 티스토리 로그인 후 '허가' 클릭\n"
        f"[bold]3.[/bold] 리다이렉트된 URL에서 [bold]code=[/bold] 뒤의 값을 복사하세요",
        title="[bold]티스토리 OAuth 인증[/bold]",
        border_style="cyan",
    ))

    code = input("code 값 붙여넣기: ").strip()

    resp = requests.get(
        "https://www.tistory.com/oauth/access_token",
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": _REDIRECT_URI,
            "code": code,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )

    if "access_token" in resp.text:
        from urllib.parse import parse_qs
        token = parse_qs(resp.text).get("access_token", [""])[0]
        console.print(Panel(
            f"[green]인증 성공![/green]\n\n"
            f".env 파일에 아래를 추가하세요:\n\n"
            f"[bold]TISTORY_ACCESS_TOKEN={token}[/bold]",
            border_style="green",
        ))
    else:
        console.print(f"[red]인증 실패:[/red] {resp.text}")


def post_to_tistory(
    article: str,
    seo_keywords: str = "",
    visibility: str | None = None,
) -> str | None:
    """
    완성된 마크다운 글을 티스토리에 등록합니다.
    visibility: "0"=비공개(기본), "3"=공개
    반환값: 등록된 포스트 URL (실패 시 None)
    """
    access_token = os.getenv("TISTORY_ACCESS_TOKEN", "")
    blog_name = os.getenv("TISTORY_BLOG_NAME", "")
    category_id = os.getenv("TISTORY_CATEGORY_ID", "0")

    if not access_token or not blog_name:
        return None

    if visibility is None:
        visibility = os.getenv("TISTORY_VISIBILITY", "0")

    title = _extract_title(article)
    html_content = _markdown_to_html(article)
    tags = _extract_tags(seo_keywords)

    resp = requests.post(
        f"{_TISTORY_API}/post/write",
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
        data = resp.json()
        tistory = data.get("tistory", {})
        if str(tistory.get("status")) == "200":
            return tistory.get("url", "")

    console.print(f"[red]티스토리 등록 실패:[/red] {resp.status_code} {resp.text[:200]}")
    return None


def _extract_title(article: str) -> str:
    """마크다운 첫 번째 H1/H2 제목을 추출합니다."""
    for line in article.splitlines():
        stripped = line.lstrip("#").strip()
        if stripped and line.startswith("#"):
            return stripped
    return "BLOOMI 큐레이션"


def _markdown_to_html(text: str) -> str:
    """마크다운을 티스토리 HTML로 변환합니다."""
    return markdown(text, extensions=["extra", "nl2br"])


def _extract_tags(seo_keywords: str) -> str:
    """SEO 키워드 문자열에서 태그를 추출합니다 (최대 10개)."""
    cleaned = re.sub(r"[#\n]", " ", seo_keywords)
    parts = [t.strip() for t in re.split(r"[,\s]+", cleaned) if t.strip()]
    return ",".join(parts[:10])
