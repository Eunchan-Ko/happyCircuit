# mac_ws_client.py (새 파일)
import asyncio
import websockets
import cv2
import numpy as np
import base64
import time
import json

async def receive_stream():
    uri = "ws://<YOUR_PI_IP>:9091" # 라즈베리파이 IP 주소 입력
    async with websockets.connect(uri) as websocket:
        print(f"Connected to {uri}")

        frame_count = 0
        start_time = time.time()

        while True:
            message_str = await websocket.recv()
            reception_time = time.time() # 메시지 수신 시간

            # 데이터 파싱
            data = json.loads(message_str)
            send_timestamp = data['timestamp']
            img_b64 = data['image']

            # 1. 전송 지연 시간 (Latency) 계산
            latency = (reception_time - send_timestamp) * 1000  # ms 단위로 변환

            # 이미지 디코딩
            img_bytes = base64.b64decode(img_b64)
            np_arr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            # 2. 이미지 처리 시간 측정
            proc_start_time = time.time()

            # === 동일한 이미지 처리 로직 ===
            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blurred_frame = cv2.GaussianBlur(gray_frame, (5, 5), 0)
            # ==============================

            proc_end_time = time.time()
            processing_time = (proc_end_time - proc_start_time) * 1000 # ms 단위

            # 3. FPS 계산
            frame_count += 1
            elapsed_time = time.time() - start_time
            fps = frame_count / elapsed_time if elapsed_time > 0 else 0

            # 결과 출력
            print(f"Latency: {latency:.2f} ms | Processing Time: {processing_time:.2f} ms | FPS: {fps:.2f}")

            # (선택) 화면에 영상 표시
            # cv2.imshow("WebSocket Stream", blurred_frame)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #     break

if __name__ == "__main__":
    try:
        asyncio.run(receive_stream())
    except KeyboardInterrupt:
        print("Client stopped.")