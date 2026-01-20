# DeepResearcher Prompts

이 폴더에는 DeepResearcher의 각 에이전트에서 사용하는 프롬프트가 저장됩니다.
코드를 수정하지 않고 프롬프트를 쉽게 수정할 수 있습니다.

## 폴더 구조

```
data/prompts/
├── README.md           # 이 파일
├── RD/                 # Research Definition (연구 정의)
│   ├── system_prompt.md     # 시스템 프롬프트 (에이전트 역할 정의)
│   ├── initial_artifact.md  # 초기 아티팩트 템플릿
│   ├── summary_prompt.md    # 요약 요청 시 사용
│   ├── initial_prompt.md    # 첫 대화 시작 시 사용
│   └── readiness_prompt.md  # 다음 단계 준비도 평가 시 사용
├── ED/                 # Experiment Design (실험 설계)
│   └── system_prompt.md     # 시스템 프롬프트
├── LR/                 # Literature Review (문헌 검토)
│   └── evaluation_prompt.md # 문헌 평가 프롬프트
└── PW/                 # Paper Writing (논문 작성)
    ├── system_prompt.md     # 시스템 프롬프트
    └── initial_artifact.md  # 초기 아티팩트 템플릿
```

## 프롬프트 수정 방법

1. 해당 폴더의 `.md` 파일을 열어 수정합니다.
2. 서버를 재시작하면 자동으로 새 프롬프트가 로드됩니다.
3. (개발 중) `reload_prompts()` 메서드로 핫 리로드 가능

## 프롬프트 카테고리

### RD (Research Definition)
연구 주제를 정의하고 연구 질문을 발전시키는 대화형 에이전트

| 파일 | 설명 |
|-----|------|
| `system_prompt.md` | 에이전트의 역할, 원칙, 응답 스타일 정의 |
| `initial_artifact.md` | 연구 정의 문서의 초기 템플릿 |
| `summary_prompt.md` | 요약 요청 시 사용되는 프롬프트 |
| `initial_prompt.md` | 새 연구 주제 제시 시 첫 응답 가이드 |
| `readiness_prompt.md` | 다음 단계 진행 준비도 평가 기준 |

### ED (Experiment Design)
연구 방법론과 실험 설계를 안내하는 에이전트

| 파일 | 설명 |
|-----|------|
| `system_prompt.md` | 실험 설계 원칙 및 가이드라인 |

### LR (Literature Review)
문헌 검토 및 평가를 수행하는 에이전트

| 파일 | 설명 |
|-----|------|
| `evaluation_prompt.md` | 문헌 체계적 평가 및 갭 분석 프롬프트 |

### PW (Paper Writing)
논문 작성을 지원하는 에이전트

| 파일 | 설명 |
|-----|------|
| `system_prompt.md` | 논문 작성 에이전트 시스템 프롬프트 |
| `initial_artifact.md` | 논문 초안 초기 템플릿 |

## 변수 (Placeholders)

프롬프트에서 사용 가능한 변수:

### RD 프롬프트
- `{topic}` - 연구 주제
- `{artifact}` - 현재 아티팩트 내용

### ED 프롬프트
- 현재 변수 없음 (정적 프롬프트)

### LR 프롬프트
- 현재 변수 없음 (정적 프롬프트)

### PW 프롬프트
- `{research_definition}` - 연구 정의 내용
- `{experiment_design}` - 실험 설계 내용

## 성숙도 표시자 (Maturity Indicators)

RD 아티팩트에서 사용되는 성숙도 표시:
- 🔴 Early Stage / Needs Work
- 🟡 Developing / Almost Ready
- 🟢 Solid / Ready

## 체크리스트 표시자

준비도 평가에서 사용:
- ✅ Ready
- ⚠️ Needs Work
- ❌ Missing

## 주의사항

1. **변수 형식 유지**: `{variable}` 형식의 변수를 삭제하지 마세요.
2. **마크다운 형식**: 프롬프트는 마크다운 형식으로 작성됩니다.
3. **인코딩**: UTF-8로 저장하세요.
4. **백업**: 수정 전 원본을 백업하세요.

## 개발자 참고

프롬프트 로더: `backend/utils/prompt_loader.py`

```python
from backend.utils.prompt_loader import PromptLoader

# 특정 프롬프트 로드
prompt = PromptLoader.load("RD", "system_prompt")

# 캐시 초기화 후 재로드
PromptLoader.clear_cache()
prompt = PromptLoader.reload("RD", "system_prompt")

# 카테고리 내 모든 프롬프트 목록
prompts = PromptLoader.list_prompts("RD")

# 모든 카테고리 목록
categories = PromptLoader.list_categories()

# Convenience 함수 사용
from backend.utils.prompt_loader import (
    load_rd_system_prompt,
    load_rd_initial_artifact,
    load_ed_system_prompt,
    load_ed_initial_artifact,
    load_pw_system_prompt,
    load_pw_initial_artifact,
    load_lr_evaluation_prompt,
)

rd_prompt = load_rd_system_prompt()
pw_prompt = load_pw_system_prompt()
lr_prompt = load_lr_evaluation_prompt()
```
