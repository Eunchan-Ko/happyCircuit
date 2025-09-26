# pi_timestamp_sender.py (새 파일)
import asyncio
import websockets
import time
import json

FRAME_RATE = 30.0 # 영상의 FPS와 반드시 일치시킬 것
connected_clients = set()

async def handler(websocket):
    global connected_clients
    connected_clients.add(websocket)
    print(f"Client connected: {websocket.remote_address}")
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.remove(websocket)

async def broadcast_timestamps():
    frame_id = 0
    while True:
        if connected_clients:
            current_timestamp = time.time()
            message = json.dumps({
                'frame_id': frame_id,
                'timestamp': current_timestamp
            })
            # 모든 클라이언트에게 전송
            await asyncio.gather(*[client.send(message) for client in connected_clients])

        frame_id += 1
        await asyncio.sleep(1.0 / FRAME_RATE)

async def main():
    server_task = websockets.serve(handler, "0.0.0.0", 9092) # 포트 충돌 방지 (9092)
    broadcast_task = asyncio.create_task(broadcast_timestamps())
    await asyncio.gather(server_task, broadcast_task)

if __name__ == "__main__":
    print("Timestamp server started on ws://0.0.0.0:9092")
    asyncio.run(main())

'''
해당 명령어가 rtsp 방식으로 소스를 전달한 방법.
rpicam-vid -t 0 --width 640 --height 480 --framerate 30   --codec h264 --profile baseline --inline --intra 60 --bitrate 3000000 -o - | ffmpeg -re -i - -c copy -f rtsp -rtsp_transport tcp   rtsp://172.20.10.3:8554/cam

서버측에서는 mediamtx 가 실행중이어야한다. 관련 .xml 파일은 다른 소스 참고.
'''