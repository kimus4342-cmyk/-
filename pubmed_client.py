import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


@dataclass
class PubMedPaper:
    title:    str
    abstract: str
    journal:  str
    year:     str
    doi:      str
    pmid:     str

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
    pmids = _esearch(query, max_results)
    if not pmids:
        return []
    return _efetch(pmids)


def _esearch(query: str, max_results: int) -> list[str]:
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
    })
    try:
        with urllib.request.urlopen(f"{_ESEARCH}?{params}", timeout=10) as resp:
            data = json.loads(resp.read())
            return data.get("esearchresult", {}).get("idlist", [])
    except Exception:
        return []


def _efetch(pmids: list[str]) -> list[PubMedPaper]:
    params = urllib.parse.urlencode({
        "db": "pubmed",
        "id": ",".join(pmids),
        "rettype": "xml",
        "retmode": "xml",
    })
    try:
        with urllib.request.urlopen(f"{_EFETCH}?{params}", timeout=15) as resp:
            xml_data = resp.read()
    except Exception:
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
    )
