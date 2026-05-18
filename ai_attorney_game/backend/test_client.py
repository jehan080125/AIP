import asyncio
import websockets
import json
import sys

async def interactive_client():
    """
    개발자가 터미널에서 로직을 테스트하기 위한 간단한 비동기 WebSocket 클라이언트입니다.
    """
    uri = "ws://localhost:8000/ws/trial"
    
    print("========================================")
    print(" AI 법정 게임 테스트 클라이언트에 오신 것을 환영합니다.")
    print(f" 서버에 연결 중... ({uri})")
    print("========================================\n")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("[System] 서버와 연결되었습니다. 심문을 시작하세요.")
            print("(종료하려면 'quit' 또는 'exit' 입력)\n")
            
            while True:
                # 1. 사용자로부터 증거 ID와 추궁할 텍스트 입력받기
                # asyncio 환경에서 input이 블로킹되지 않도록 asyncio.to_thread 사용
                action_input = await asyncio.to_thread(input, "행동 타입 (question, present, press 중 택 1, 기본값: question): ")
                action_input = action_input.strip().lower()
                
                if action_input in ['quit', 'exit']:
                    print("[System] 테스트를 종료합니다.")
                    break
                
                action = action_input if action_input in ["question", "present", "press"] else "question"
                
                evidence_id = await asyncio.to_thread(input, "제시할 증거 ID (없으면 Enter): ")
                evidence_id = evidence_id.strip()
                
                text = await asyncio.to_thread(input, "추궁/심문 텍스트: ")
                text = text.strip()
                
                # 2. JSON 페이로드 구성
                payload = {
                    "action": action,
                    "target": "def_001",  # 고정된 대상
                    "evidence_id": evidence_id if evidence_id else None,
                    "text": text
                }
                
                # 3. 서버로 패킷 전송
                await websocket.send(json.dumps(payload))
                print("\n[System] 발언을 전송하고 AI의 응답을 기다리는 중...\n")
                
                # 4. 서버 응답 수신 및 출력
                response = await websocket.recv()
                response_data = json.loads(response)
                
                if response_data.get("status") == "error":
                    print(f"[Error] {response_data.get('message')}")
                    print(response_data)
                elif response_data.get("status") == "breakdown":
                    # 붕괴(Breakdown) 상태 시 특별한 출력 포맷
                    print(f"💥 [BREAKDOWN] 💥")
                    print(f"피고인: {response_data.get('text')}")
                    print(f"(규제 AI 기각 사유: {response_data.get('reason')})\n")
                else:
                    # 일반적인 대답 통과 시
                    speaker = response_data.get("speaker", "피고인").upper()
                    print(f"[{speaker}]: {response_data.get('text')}\n")
                    
    except ConnectionRefusedError:
        print("[Error] 서버에 연결할 수 없습니다. FastAPI 서버(backend.main)가 8000번 포트에서 실행 중인지 확인하세요.")
    except Exception as e:
        print(f"[Error] 예상치 못한 오류 발생: {e}")

if __name__ == "__main__":
    # ---------------------------------------------------------
    # 클라이언트 실행 방법:
    # 프로젝트 루트 디렉토리에서 아래 명령어를 실행하세요.
    # python backend/test_client.py
    # (주의: websockets 라이브러리가 설치되어 있어야 합니다. pip install websockets)
    # ---------------------------------------------------------
    try:
        asyncio.run(interactive_client())
    except KeyboardInterrupt:
        print("\n[System] 강제 종료되었습니다.")
        sys.exit(0)
