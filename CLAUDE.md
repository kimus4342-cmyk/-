# BLOOMI — 4050 뷰티 큐레이션 멀티 에이전트

## 작업 규칙 (필수 준수)

코드 수정, 파일 변경, 설정 추가 등 모든 액션 전에 반드시 사용자에게 먼저 설명하고 확인을 받을 것.
사용자가 명확히 "해줘", "추가해", "수정해" 등 실행 지시를 한 경우에만 진행한다.
질문에 답변하거나 효과·방법을 설명하는 것은 실행 지시가 아니다.

## 프로젝트 개요
OpenAI API 기반 4단계 파이프라인으로 한국 40-50대 여성 타깃 스킨케어 블로그 글을 자동 생성한다.

**파이프라인 순서:** 리서치 에이전트 → 작성 에이전트 → 고도화 에이전트 → 검수 에이전트
(검수를 마지막에 두어, 고도화 단계가 추가하는 트렌드·SEO·경쟁 차별화 내용도 발행 전 검수를 반드시 거치도록 함)

## 실행 방법

```bash
# 환경 변수 설정
cp .env.example .env   # OPENAI_API_KEY 입력

# 의존성 설치
pip install -r requirements.txt

# 실행
python main.py
```

Windows에서는 `run.bat` 사용 가능.

생성된 글은 `주제명_YYYYMMDD_NNN.md` 형식으로 저장된다. (예: `히알루론산_20260510_001.md`)

## 파일 구조

| 파일 | 역할 |
|------|------|
| `main.py` | 진입점, 파일 저장 |
| `pipeline.py` | 4단계 파이프라인 오케스트레이션 |
| `config.py` | 모델명, 토큰 한도, 시스템 프롬프트 전체 |
| `models.py` | Pydantic 데이터 모델 (`ResearchOutput`, `ReviewResult`, `EnhancementResult`) |
| `research_agent.py` | ① 리서치 에이전트 |
| `writing_agent.py` | ② 작성 에이전트 |
| `enhancement_agent.py` | ③ 고도화 에이전트 (트렌드·SEO·경쟁 차별화) |
| `review_agent.py` | ④ 검수 에이전트 (고도화 이후 실행되는 최종 발행 게이트) |

## 모델 설정 (`config.py`)

| 상수 | 기본값 | 용도 |
|------|--------|------|
| `RESEARCH_MODEL` | `gpt-4o-mini-search-preview` | 웹 검색 포함 리서치 |
| `WRITING_MODEL` | `gpt-4o` | 블로그 초안 작성 |
| `REVIEW_MODEL` | `gpt-4o` | 24항목 체크리스트 검수 |
| `ENHANCEMENT_SEARCH_MODEL` | `gpt-4o-mini-search-preview` | 트렌드·SEO·경쟁 분석 (웹 검색) |
| `ENHANCEMENT_MODEL` | `gpt-4o` | 분석 결과 글 반영 |

## 데이터 모델 (`models.py`)

**ResearchOutput** — 리서치 에이전트 출력
- `topic`: 선정 성분/주제
- `skin_concern`: 4050 피부 고민
- `core_message`: 글 전체 핵심 메시지
- `key_insights`: 임상 인사이트 (700자 이상)
- `editorial_angle`: 각도 유형 + 선택 이유 + 오프닝 훅
- `products`: `Product` 리스트 (name, feature, price, url, ingredients)

**ReviewResult** — 검수 에이전트 출력
- `score`: 1~10 (8~10 승인, 6~7 부분 수정, 1~5 전면 재작성)
- `feedback`: 24항목 체크리스트 결과
- `final_article`: 최종 완성 글

**EnhancementResult** — 고도화 에이전트 출력
- `trends_found`: 조사된 최신 트렌드 데이터
- `seo_keywords`: SEO 검색 키워드 목록
- `competitor_gaps`: 경쟁 콘텐츠 차별화 포인트
- `enhanced_article`: 고도화 최종본

## 시스템 프롬프트 수정 지침

프롬프트는 모두 `config.py`의 `*_SYSTEM_PROMPT` 상수에 집중되어 있다.

- **리서치 프롬프트**: 출력 형식 섹션(`=== TOPIC ===` 등) 변경 시 `research_agent.py`의 파싱 로직도 함께 수정
- **작성 프롬프트**: 글 구조(① 고정 요소 / ② 중간 섹션) 변경 시 검수 체크리스트(24항목)도 정합성 확인
- **검수 프롬프트**: 체크리스트 항목 수 변경 시 판정 기준(Yes 23개 이상 등) 수치도 함께 조정
- **고도화 검색 프롬프트** (`ENHANCEMENT_SEARCH_PROMPT`): 출력 섹션(`=== TRENDS ===` 등) 변경 시 `enhancement_agent.py`의 `_parse_search()` 로직도 함께 수정
- **고도화 반영 프롬프트** (`ENHANCEMENT_APPLY_PROMPT`): 출력 섹션(`=== ENHANCED_ARTICLE ===`) 변경 시 `_parse_enhanced()` 로직도 함께 수정

## 주의사항

- `RESEARCH_MODEL`은 `web_search` 도구를 지원하는 모델만 사용 가능 (현재 `gpt-4o-mini-search-preview`)
- 리서치 프롬프트에서 레티놀은 반복 선정 금지로 명시되어 있음
- 제품 플레이스홀더(`[정확한 제품명]` 등) 그대로 출력되면 `pipeline.py` 또는 `research_agent.py`의 필터 로직 확인
