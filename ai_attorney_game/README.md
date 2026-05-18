# AI Attorney Game

AI 기반 법정/추리 시뮬레이션 웹 게임입니다. 현재 메인 플레이 흐름은 `episode -> trial -> stage`이며, MVP의 우선 구현 대상은 `vs_witness` 스테이지입니다.

## 실행 방법

### Backend 

```powershell
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 수정(backend, powershell)
"""
cd C:\Users\jehan\Documents\GitHub\AIP\ai_attorney_game> 
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.main:app --reload --port 8000
"""
### 수정(frontend, cmd)
"""
cd C:\Users\jehan\Documents\GitHub\AIP\ai_attorney_game\frontend 
npm run dev
""" 


프로젝트 루트에서 실행할 경우:

```powershell
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

### Frontend

```powershell
cd frontend
Remove-Item -Recurse -Force node_modules
npm install
npm run dev
```

zip에 포함된 `node_modules`가 있다면 그대로 쓰지 말고 `npm install`을 다시 실행하세요.

### 접속

[http://localhost:5173](http://localhost:5173)

## 환경 변수 예시

```env
USE_REDIS=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
LLM_PROVIDER=auto
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```

- `USE_REDIS=false`이면 Redis 없이 인메모리 상태 저장소로 실행됩니다.
- `OPENAI_API_KEY`가 있으면 OpenAI를 우선 사용합니다.
- OpenAI 호출이 실패하거나 API 키가 없으면 mock 모드로 자동 fallback됩니다.
- API 키가 있어도 mock으로만 확인하려면 `LLM_PROVIDER=mock`으로 실행하세요.
- Gemini는 현재 사용하지 않습니다.

## 현재 플레이 구조

1. 에피소드 선택
2. 난이도 선택
   - easy: 조력자/힌트 활성화, 생명 여유
   - hard: 조력자 힌트 비활성화
3. 현장 조사에서 증거 수집
4. 법정 시작
5. `vs_witness`에서 고정 증언 공격
6. 증거 또는 발언 기록 최대 2개 선택
7. 100자 이내 자유 주장 제출
8. StageEngine이 판정과 상태 변화를 계산
9. 판사는 이유를 설명하고, 증인은 감정적으로 반응
10. 필요할 때만 검사가 짧게 개입
11. 증인 멘탈이 0이면 스테이지 클리어
12. `vs_prosecutor`는 피고인 신문 버튼을 통한 placeholder 공방으로 유지

## Mock 모드 수동 테스트 정답

### 1스테이지 첫 공격

선택 증거: `ev_003` 가로등 정비 기록

```text
가로등이 꺼져 있었다면 증인이 피고인을 정확히 식별했다는 말은 신빙성이 낮습니다.
```

### 증인 반박 1 공격

선택 증거: `ev_002` 현장 CCTV 기록, `stmt_guard_1` 증인의 이전 발언

```text
처음엔 직접 봤다더니 이제는 옷차림 추정이라고 말이 바뀌었습니다.
```

### 증인 반박 2 공격

선택 증거: `ev_002` 현장 CCTV 기록, `counter_guard_1` 증인의 반박 발언

```text
CCTV 인물은 피고인과 다르니 기억만으로 특정할 수 없습니다.
```

### vs_prosecutor placeholder

1. `피고인 신문` 버튼을 누릅니다.
2. 선택 증거: 피고인 발언 기록, `ev_002`

```text
피고인 신문과 CCTV 기록을 종합하면 검사의 논리는 단정에 가깝습니다.
```

같은 방식으로 몇 차례 설득도를 올리면 episode score와 ending이 표시됩니다.

## 테스트

```powershell
python -m pytest
```

Frontend:

```powershell
cd frontend
npm run build
npm run lint
```
