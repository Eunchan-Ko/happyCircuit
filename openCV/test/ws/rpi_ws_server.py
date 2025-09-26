# pi_stream_ws_server.py (일부 수정)
from picamera2 import Picamera2
import cv2
import asyncio
import websockets
import base64
import numpy as np
import time
import json # json 라이브러리 추가
# ... (기존 코드)
connected_clients = set()

async def video_stream_handler(websocket):
    """클라이언트가 접속하면 호출되며, 영상 스트림을 전송합니다."""
    print(f"클라이언트 {websocket.remote_address} 접속.")
    connected_clients.add(websocket)
    try:
        # 클라이언트가 연결을 끊을 때까지 계속 실행
        await websocket.wait_closed()
    finally:
        print(f"클라이언트 {websocket.remote_address} 접속 종료.")
        connected_clients.remove(websocket)

async def broadcast_frames():
    # 1. Picamera2 객체 생성 및 설명
    picam2 = Picamera2()
    picam2.configure(picam2.create_preview_configuration(main={"format": 'XRGB8888', "size": (640, 480)}))
    picam2.start()

    camera_ok = picam2.started
    # 카메라 해상도 설정 (604 x 480)
    # asyncio의 현재 이벤트 루프를 가져옵니다.
    loop = asyncio.get_running_loop()

    while True:
        frame = picam2.capture_array()

        # JPEG 인코딩
        retval, buffer = await loop.run_in_executor(
            None, cv2.imencode, '.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90]
        )
        if not retval:
            continue

        # Base64 인코딩
        jpg_as_text = base64.b64encode(buffer).decode('utf-8')

        # [수정] 현재 시간을 타임스탬프로 찍어서 JSON으로 만듦
        current_timestamp = time.time()
        message = json.dumps({
            'timestamp': current_timestamp,
            'image': jpg_as_text
        })

        if connected_clients:
            await asyncio.wait([client.send(message) for client in connected_clients])

        await asyncio.sleep(0.01) # CPU 부하 조절

async def main():
    """메인 함수: 웹소켓 서버와 프레임 방송을 함께 실행합니다."""
    # 0.0.0.0: 모든 IP에서의 접속을 허용, 5001: 포트 번호
    server = await websockets.serve(video_stream_handler, "0.0.0.0", 9091)
    print("웹소켓 서버가 포트 9091에서 시작되었습니다.")

    # 프레임 방송 작업 실행
    # broadcast_frames 함수를 별도의 비동기 작업으로 생성
    broadcast_task = asyncio.create_task(broadcast_frames())

    # 서버 작업과 방송 작업을 '함께' 실행
    await asyncio.gather(server.wait_closed(), broadcast_task)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("서버를 종료합니다.")