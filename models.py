from pydantic import BaseModel, field_validator

class ResearchOutput(BaseModel):
    topic: str
    topic_type: str = ""  # 성분심화 / 카테고리비교 / 고민해결 / 뷰티디바이스
    skin_concern: str
    core_message: str
    key_insights: str
    editorial_angle: str = ""  # 각도 유형 + 선택 이유 + 오프닝 훅
    reader_questions: str = ""  # 독자가 검색 전 궁금해할 질문 5개 — 작성 단계 섹션 흐름 설계용
    keyword: str = ""  # 주제 선정 단계에서 쓰인 네이버 검색용 핵심 키워드 (이력 기록용)
    paper_titles: list[str] = []  # PubMed에서 실제로 확보한 논문 제목 목록 (검수 단계 인용 대조용)

class ReviewInsights(BaseModel):
    positive_patterns: str = ""
    negative_patterns: str = ""
    common_mistakes: str = ""
    sources: str = ""  # 검색에서 확인한 URL (없으면 빈 문자열)

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
