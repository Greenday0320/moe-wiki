# 교육부 위키 — 새 채팅방에서 이어가는 법

## 지금까지 한 일
- 교육부 보도자료(2026-07-08 ~ 2026-07-29, 총 42건)를 위키 형태(목차+문단, 나무위키 스타일)로 변환.
- 조직도 기반 분류 체계로 자동 분류(초중등교육/고등교육/평생·직업교육/유아교육·보육/디지털·인공지능교육/학생지원·복지/국제교육협력/교육행정·정책총괄/미분류).
- `index.html`을 열면 전체 결과 확인 가능.
- (2026-07-29) 한때 PWA(설치 가능한 웹앱)로 전환했었으나(manifest.json, service-worker.js, offline.html, assets/app.js, assets/icons/, serve.py), **다시 순수 정적 HTML로 되돌림**(2026-07-30). 위 파일들은 모두 삭제했고, `generate_wiki.py`의 세 템플릿에서 manifest link/apple-touch-icon/theme-color/service-worker 등록 스크립트를 제거함. `file://`로 그냥 열어도 됨(서버 불필요).
- (2026-07-30) 2024년 샘플 문서(2024-hwabangi-jinrocheheom) 삭제 — 현재 총 42건.
- (2026-07-30) **각 문서에 "배경/맥락" 문단 추가**: `data/<slug>.meta.json`의 `background` 필드(문자열)에 제도의 유래·법적근거·연혁 등을 적어두면, 부제목 아래 파란 테두리 박스(`.wiki-background`, CSS에 정의)로 표시됨. 42건 전부 채워둠(`add_backgrounds.py`가 그 작업을 한 1회성 스크립트 — 새 문서 추가 시 같은 패턴으로 재사용 가능). 배경 문단은 반드시 원문에 있던 사실만 쓰고 추측/외부지식으로 없는 사실을 지어내지 말 것(예: "매년 X월 X일에 열린다" 같은 미확인 정기성 주장 금지).
- (2026-07-30) **나무위키식 키워드 자동 링크** 추가: `generate_wiki.py`의 `KEYWORD_LINKS` 리스트에 `{"phrase": "문구", "targets": {소스slug: 링크할slug}}` 형태로 등록하면, 그 문구가 본문(배경 포함)에 처음 등장하는 곳만 자동으로 다른 문서 링크가 됨(`apply_keyword_links()` 함수). 지금은 43개 기존 문서끼리만 연결하는 정책이라 새 키워드 "허브 문서"는 만들지 않음 — 새 문서 추가 시 기존 문서와 겹치는 고유명사/프로그램명이 있으면 KEYWORD_LINKS에 항목을 추가할 것.
- (2026-07-30) **중요 버그 수정**: `is_title_chunk()`가 제목 앞 8글자가 본문 "어디에" 있든 매칭해버려서, 제목의 키워드가 본문 중간에 재등장하면(예: 제목이 "3대 메가프로젝트..."인데 본문 뒷부분에서도 "3대 메가프로젝트 관련 분야에서는"처럼 다시 언급되는 경우) 그 문단 전체가 통째로 사라지는 버그가 있었음. 문단이 제목으로 "시작하는지"만 보도록 고쳐서(`startswith`) 42건 전체 재빌드함 — 이 버그로 인해 이전에 빠졌던 문단들이 복원됨.
- (2026-07-30) 모바일 CSS 개선(`assets/style.css`의 `@media (max-width: 600px)` 블록): 여백/폰트크기/터치 영역 확대, 표 가로스크롤 관성 스크롤 추가. 레이아웃/색상 구조는 그대로(나무위키 스타일 유지 요청에 따름).

## 새 채팅방에서 할 말 (예시)
> "C:\Users\82103\Desktop\교육부위키 프로젝트 이어서 작업할 거야. CONTINUE.md 읽고 최근 N일치 보도자료 추가로 처리해줘."

## 파이프라인 구조 (반드시 이 순서로)
1. **`fetch_batch.py --days N`** — 목록 페이지 스크래핑 + 첨부파일(hwp/hwpx/pdf) 자동 다운로드. 순수 파이썬, kordoc 불필요. 이미 받은 파일은 재다운로드 안 함. 결과는 `data/_batch_manifest.json`에 누적 기록.
2. **각 문서마다 (Claude가 직접 해야 함, 스크립트로 자동화 불가):**
   - `mcp__kordoc__parse_document`로 `raw/<boardSeq>.hwpx` 파싱 → 마크다운 텍스트 획득
   - 너무 긴 문서(법령 전문, 수백 행 표 등)는 요약해서 `data/<boardSeq>.md`로 저장 (원본 그대로 베끼지 말 것 — 컨텍스트 낭비)
   - `python generate_wiki.py --ingest <boardSeq>` — manifest에서 제목/날짜 가져오고, 담당부서 표에서 부서명 추출해 `data/<boardSeq>.meta.json` 생성
   - `python generate_wiki.py <boardSeq>` — 실제 위키 HTML(`articles/<boardSeq>.html`) 생성
3. 전부 끝나면 **`python generate_wiki.py --rebuild-index`** — `index.html` + `categories/*.html` 갱신.

## 알아둘 것
- **분류 기준**: 목록 페이지의 "담당부서"는 항상 "홍보담당관"이라 못 씀. 반드시 첨부파일 본문 안 "담당 부서" 표에서 실제 부서(예: "학교정책실 공교육진흥과")를 추출해야 함 → `generate_wiki.py`의 `extract_contact()` 함수가 담당. "책임자" 셀 바로 왼쪽 셀을 부서명으로 보는 방식이라 단독/공동 부처 발표 둘 다 대응하지만, **교육부가 아닌 타 부처가 표에서 먼저 나오는 공동 보도자료는 미분류로 빠짐** (예: 문체부·기획예산처 주관 공동자료). 이런 건 수동으로 봐줘야 함.
- **분류 체계**: `category_map.json`에 대분류/중분류 + 부서명→분류 매핑 테이블이 있음. 새로운 부서명이 나오면 (예: 조직개편, 새로운 정책관실) 여기에 추가하면 됨.
- **오래된 문서(2024년 등)**: 그때 조직도가 지금과 달라서 미분류로 빠지는 게 정상. 필요하면 `category_map.json`에 과거 조직명도 추가 가능.
- **원본 파일 위치**: `raw/<boardSeq>.hwpx` (또는 hwp/pdf). 목록 URL: `https://www.moe.go.kr/boardCnts/listRenew.do?boardID=294&m=020402&s=moe`

## 다음에 이어서 할 만한 것
- 더 이전 날짜(예: 2026-06월 이전) 보도자료 추가 (새 문서에도 background 문단 + 필요시 KEYWORD_LINKS 등록 잊지 말 것)
- 미분류 몇 건 수동 재분류 또는 category_map.json 보강
