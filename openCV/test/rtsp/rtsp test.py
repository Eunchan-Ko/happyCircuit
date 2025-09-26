# mac_hybrid_receiver.py (새 파일)
import cv2
import time
import json
import threading
import websockets
import asyncio
from collections import deque

# 스레드 간 데이터 공유를 위한 변수
timestamps = {} # {frame_id: timestamp}
latest_video_frame_id = -1
MAX_BUFFER_SIZE = 300 # 메모리 관리를 위해 최대 300개 타임스탬프만 저장

def video_thread_func():
    """RTSP 비디오를 수신하고 프레임 카운트를 업데이트하는 스레드"""
    global latest_video_frame_id

    uri = "rtsp://localhost:8554/cam"
    print("비디오 스레드: RTSP 연결 시도 중...")
    cap = cv2.VideoCapture(uri)
    print("비디오 스레드: 연결 시도 완료. 스트림 상태 확인 중...")
    if not cap.isOpened():
        print("Error: Cannot open RTSP stream")
        return
    print("✅ Success: 스트림이 성공적으로 열렸습니다. 프레임 읽기를 시작합니다.")
    frame_id_counter = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Video stream ended. Exiting video thread.")
            break

        latest_video_frame_id = frame_id_counter
        frame_id_counter += 1

        # (선택) 여기에 이미지 처리 로직을 넣고 처리 시간 측정 가능
        # cv2.imshow("RTSP Stream", frame)
        # if cv2.waitKey(1) & 0xFF == ord('q'):
        #     break

    cap.release()
    cv2.destroyAllWindows()

async def websocket_client_func():
    """WebSocket으로 타임스탬프를 수신하고 딕셔너리에 저장하는 스레드"""
    uri = "ws://172.20.10.2:9092" # 타임스탬프 서버의 IP와 포트
    async with websockets.connect(uri) as websocket:
        print("Connected to timestamp server.")
        while True:
            message_str = await websocket.recv()
            data = json.loads(message_str)
            frame_id = data['frame_id']
            timestamps[frame_id] = data['timestamp']
            # 오래된 타임스탬프 데이터 삭제
            if len(timestamps) > MAX_BUFFER_SIZE:
                oldest_key = min(timestamps.keys())
                del timestamps[oldest_key]


def run_websocket_client():
    asyncio.run(websocket_client_func())

if __name__ == "__main__":
    # 1. 비디오 수신 스레드 시작
    video_thread = threading.Thread(target=video_thread_func)
    video_thread.daemon = True
    video_thread.start()

    # 2. 타임스탬프 수신 스레드 시작
    ws_thread = threading.Thread(target=run_websocket_client)
    ws_thread.daemon = True
    ws_thread.start()

    print("Receiver started. Press Ctrl+C to stop.")

    # 3. 메인 스레드에서 1초마다 지연 시간 계산 및 출력
    try:
        while True:
            time.sleep(1)
            current_frame_id = latest_video_frame_id

            if current_frame_id > 0 and current_frame_id in timestamps:
                reception_time = time.time()
                send_timestamp = timestamps[current_frame_id]
                latency = (reception_time - send_timestamp) * 1000 # ms
                print(f"Current Frame: {current_frame_id}, Latency: {latency:.2f} ms")

    except KeyboardInterrupt:
        print("Stopping...")