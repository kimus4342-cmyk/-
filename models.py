from pydantic import BaseModel, field_validator

class Product(BaseModel):
    name: str
    feature: str
    price: str
    url: str
    ingredients: str = ""  # 주요 성분 목록 (레티놀 농도 + 보습/진정 성분 등)

class ResearchOutput(BaseModel):
    topic: str
    topic_type: str = ""  # 성분심화 / 카테고리비교 / 고민해결 / 뷰티디바이스
    skin_concern: str
    core_message: str
    key_insights: str
    editorial_angle: str = ""  # 각도 유형 + 선택 이유 + 오프닝 훅
    products: list[Product]

class ReviewResult(BaseModel):
    score: int
    feedback: str
    final_article: str

    @field_validator("score")
    def score_range(cls, v):
        if not (1 <= v <= 10):
            raise ValueError(f"점수는 1~10 사이여야 해요. 받은 값: {v}")
        return v


class EnhancementResult(BaseModel):
    trends_found: str
    seo_keywords: str
    competitor_gaps: str
    enhanced_article: str
