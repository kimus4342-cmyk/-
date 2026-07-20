import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
_SS_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"

# NCBI API 키가 있으면 rate limit 3→10 req/s로 올라감
# .env에 NCBI_API_KEY=xxx 설정 (없어도 동작)
_NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")


@dataclass
class PubMedPaper:
    title:    str
    abstract: str
    journal:  str
    year:     str
    doi:      str
    pmid:     str
    source:   str = "pubmed"  # "pubmed" | "semantic_scholar"

    @property
    def url(self) -> str:
        return f"https://doi.org/{self.doi}" if self.doi else f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"

    def format_for_prompt(self) -> str:
        lines = [
            f"- 제목: {self.title}",
            f"  저널: {self.journal} ({self.year})",
            f"  URL: {self.url}",
        ]
        if self.abstract:
            snippet = self.abstract[:600] + ("..." if len(self.abstract) > 600 else "")
            lines.append(f"  초록: {snippet}")
        return "\n".join(lines)


def search_papers(query: str, max_results: int = 4) -> list[PubMedPaper]:
    """PubMed 우선 검색, 결과 없으면 Semantic Scholar로 자동 fallback."""
    papers = _pubmed_search(query, max_results)
    if papers:
        return papers
    return _semantic_scholar_search(query, max_results)


# ── PubMed ──────────────────────────────────────────────

def _pubmed_search(query: str, max_results: int) -> list[PubMedPaper]:
    pmids = _esearch(query, max_results)
    if not pmids:
        return []
    return _efetch(pmids)


def _esearch(query: str, max_results: int) -> list[str]:
    params: dict = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
    }
    if _NCBI_API_KEY:
        params["api_key"] = _NCBI_API_KEY

    url = f"{_ESEARCH}?{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=12) as resp:
                data = json.loads(resp.read())
                return data.get("esearchresult", {}).get("idlist", [])
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
    return []


def _efetch(pmids: list[str]) -> list[PubMedPaper]:
    params: dict = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "xml",
        "retmode": "xml",
    }
    if _NCBI_API_KEY:
        params["api_key"] = _NCBI_API_KEY

    url = f"{_EFETCH}?{urllib.parse.urlencode(params)}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                xml_data = resp.read()
            break
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                return []

    papers = []
    try:
        root = ET.fromstring(xml_data)
        for article in root.findall(".//PubmedArticle"):
            p = _parse_article(article)
            if p.title:
                papers.append(p)
    except ET.ParseError:
        pass
    return papers


def _parse_article(article: ET.Element) -> PubMedPaper:
    def text(path: str) -> str:
        el = article.find(path)
        return "".join(el.itertext()).strip() if el is not None else ""

    abstract_parts = []
    for el in article.findall(".//AbstractText"):
        label = el.get("Label", "")
        content = "".join(el.itertext()).strip()
        abstract_parts.append(f"{label}: {content}" if label else content)

    doi = ""
    for id_el in article.findall(".//ArticleId"):
        if id_el.get("IdType") == "doi":
            doi = (id_el.text or "").strip()
            break

    pmid_el = article.find(".//PMID")
    year_raw = text(".//PubDate/Year") or text(".//PubDate/MedlineDate")

    return PubMedPaper(
        title    = text(".//ArticleTitle"),
        abstract = " ".join(abstract_parts),
        journal  = text(".//Journal/Title") or text(".//MedlineTA"),
        year     = year_raw[:4] if year_raw else "",
        doi      = doi,
        pmid     = pmid_el.text.strip() if pmid_el is not None else "",
        source   = "pubmed",
    )


# ── Semantic Scholar fallback ────────────────────────────

def _semantic_scholar_search(query: str, max_results: int) -> list[PubMedPaper]:
    """API 키 불필요. 무료 공개 API."""
    params = urllib.parse.urlencode({
        "query": query,
        "limit": max_results,
        "fields": "title,abstract,year,authors,venue,externalIds",
    })
    url = f"{_SS_SEARCH}?{params}"

    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "BLOOMI-research/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            break
        except Exception:
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                return []

    papers = []
    for item in data.get("data", []):
        if not item.get("title"):
            continue
        ext = item.get("externalIds") or {}
        doi  = ext.get("DOI", "")
        pmid = ext.get("PubMed", "")
        papers.append(PubMedPaper(
            title    = item.get("title", ""),
            abstract = (item.get("abstract") or "")[:800],
            journal  = item.get("venue", ""),
            year     = str(item.get("year", "")),
            doi      = doi,
            pmid     = str(pmid),
            source   = "semantic_scholar",
        ))
    return papers
