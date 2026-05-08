from dataclasses import dataclass


@dataclass
class Product:
    name: str
    feature: str
    price: str
    url: str


@dataclass
class ResearchOutput:
    topic: str
    skin_concern: str
    core_message: str   # 글 전체가 전달할 핵심 메시지 1~3줄
    key_insights: str
    products: list[Product]


@dataclass
class ReviewResult:
    score: int
    feedback: str
    final_article: str
