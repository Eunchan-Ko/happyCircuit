# mac_hybrid_receiver.py (새 파일)
import cv2
import time
import json
import threading
import websockets
import asyncio
from collections import deque
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import csv

# 스레드 간 데이터 공유를 위한 변수
timestamps = {} # {frame_id: timestamp}
MAX_BUFFER_SIZE = 300 # 메모리 관리를 위해 최대 300개 타임스탬프만 저장

def save_graphs(data_points):
    """matplotlib을 사용하여 성능 및 지연 시간 그래프를 파일로 저장합니다."""
    if not data_points:
        print("데이터 포인트가 없어 그래프를 생성할 수 없습니다.")
        return

    times = [dp['time'] for dp in data_points]
    fps_values = [dp['fps'] for dp in data_points]
    bandwidth_values = [dp['bandwidth'] for dp in data_points]
    latency_values = [dp['avg_latency_ms'] for dp in data_points]

    # --- 통합 성능 그래프 (FPS, Bandwidth) ---
    fig, ax1 = plt.subplots(figsize=(12, 6))
    color = 'tab:blue'
    ax1.set_xlabel("Time (seconds)")
    ax1.set_ylabel("FPS", color=color)
    ax1.plot(times, fps_values, color=color, label='FPS')
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, axis='y', linestyle='--', alpha=0.7)
    ax1.set_ylim(0, max(fps_values) * 1.2 if fps_values else 40)

    ax2 = ax1.twinx()
    color = 'tab:orange'
    ax2.set_ylabel("Bandwidth (kbps)", color=color)
    ax2.plot(times, bandwidth_values, color=color, label='Bandwidth (kbps)')
    ax2.tick_params(axis='y', labelcolor=color)

    plt.title("FPS and Bandwidth Over Time (RTSP)")
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc='upper left')

    fig.tight_layout()
    plt.savefig("performance_over_time_rtsp.png")
    plt.close()
    print("✅ 통합 성능 그래프가 'performance_over_time_rtsp.png'로 저장되었습니다.")

    # --- 지연 시간 그래프 (Latency) ---
    plt.figure(figsize=(12, 6))
    plt.plot(times, latency_values, color='tab:green', label='Avg Latency (ms)')
    plt.xlabel("Time (seconds)")
    plt.ylabel("Avg Latency (ms)")
    plt.title("Average Latency Over Time (RTSP)")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig("latency_over_time_rtsp.png")
    plt.close()
    print("✅ 평균 지연 시간 그래프가 'latency_over_time_rtsp.png'로 저장되었습니다.")

def save_csv(data_points):
    """수집된 데이터를 CSV 파일로 저장합니다."""
    if not data_points:
        print("데이터 포인트가 없어 CSV 파일을 생성할 수 없습니다.")
        return
    
    keys = data_points[0].keys()
    with open('streaming_data_rtsp.csv', 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(data_points)
    print("✅ 데이터가 'streaming_data_rtsp.csv'로 저장되었습니다.")

def save_report(data_points):
    """그래프와 CSV를 저장하는 리포트 생성 함수"""
    print("\n" + "="*50)
    print("데이터 수집 완료. 리포트를 생성합니다...")
    print("="*50)

    if not data_points:
        print("수집된 데이터가 없어 리포트를 생성할 수 없습니다.")
        print("RTSP 스트림이 정상적으로 시작되었는지, 1초 이상 실행되었는지 확인해주세요.")
        print("="*50 + "\n")
        return

    save_graphs(data_points)
    save_csv(data_points)
    print("="*50)
    print("모든 리포트 생성이 완료되었습니다.")
    print("="*50 + "\n")

def video_thread_func():
    """RTSP 비디오를 수신하고 프레임 카운트, FPS, 대역폭, 지연 시간을 계산하는 스레드"""
    uri = "rtsp://localhost:8554/cam"
    print("비디오 스레드: RTSP 연결 시도 중...")
    cap = cv2.VideoCapture(uri)
    print("비디오 스레드: 연결 시도 완료. 스트림 상태 확인 중...")
    if not cap.isOpened():
        print("Error: Cannot open RTSP stream")
        return
    print("✅ Success: 스트림이 성공적으로 열렸습니다. 프레임 읽기를 시작합니다.")
    
    # --- 계산 및 데이터 수집 변수 초기화 ---
    # frame_id_counter는 동기화 문제로 더 이상 사용하지 않습니다.
    frame_count = 0
    total_bytes = 0
    latencies = []
    start_time = time.time()

    # --- 데이터 수집 설정 ---
    COLLECTION_DURATION = 600  # 10분 = 600초
    data_points = []
    collection_start_time = time.time()
    is_collecting = True
    print(f"데이터 수집을 {COLLECTION_DURATION}초 동안 시작합니다...")
    # -------------------------
    i=1
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Video stream ended. Exiting video thread.")
            if is_collecting and len(data_points) > 1:
                save_report(data_points[1:])
            break
        
        reception_time = time.time()
        
        # 로컬 카운터(frame_id_counter)를 사용하는 대신, WebSocket으로 수신된 타임스탬프 중
        # 가장 오래된 것을 현재 프레임과 매칭합니다. 이 방식은 네트워크로 인한 프레임 드랍에
        # 더 강건하여 레이턴시를 더 정확하게 측정할 수 있습니다.
        if timestamps:
            oldest_frame_id = min(timestamps.keys())
            send_timestamp = timestamps[oldest_frame_id]
            latency = (reception_time - send_timestamp) * 1000 # ms
            
            # 시계 불일치로 인해 발생할 수 있는 음수 지연시간을 필터링합니다.

            latencies.append(latency)

            del timestamps[oldest_frame_id]

        frame_count += 1
        if frame is not None:
            total_bytes += frame.nbytes
        
        # frame_id_counter는 더 이상 필요 없습니다.

        current_time = time.time()
        elapsed_time = current_time - start_time
        if elapsed_time >= 1.0:
            fps = frame_count / elapsed_time
            bandwidth_kbps = (total_bytes / 4) / (elapsed_time * 1024) /10
            
            # 측정된 레이턴시가 없을 경우, 0으로 기록하면 그래프가 왜곡됩니다.
            # 대신 np.nan (Not a Number)으로 처리하여 데이터가 없음을 명시적으로 나타냅니다.
            # Matplotlib은 np.nan 값을 그래프에서 빈 공간으로 처리합니다.
            avg_latency = np.mean(latencies) if latencies else np.nan

            print(f"{i}sample. FPS: {fps:.2f}, Bandwidth: {bandwidth_kbps:.2f} kbps, Avg Latency: {avg_latency:.2f} ms")
            i = i+1
            if is_collecting:
                collection_elapsed_time = current_time - collection_start_time
                
                # round() 함수는 np.nan을 처리하지 못하므로, 값을 저장하기 전에 확인합니다.
                latency_to_store = avg_latency if np.isnan(avg_latency) else round(avg_latency, 2)

                data_points.append({
                    'time': round(collection_elapsed_time, 2),
                    'fps': round(fps, 2),
                    'bandwidth': round(bandwidth_kbps, 2),
                    'avg_latency_ms': latency_to_store
                })

                if collection_elapsed_time >= COLLECTION_DURATION:
                    is_collecting = False
                    if len(data_points) > 1:
                        save_report(data_points[1:])
                    else:
                        print("수집된 데이터가 부족하여 리포트를 생성할 수 없습니다.")
                    print("데이터 수집이 완료되었습니다. 프로그램은 계속 실행됩니다.")

            # Reset counters
            frame_count = 0
            total_bytes = 0
            latencies = []
            start_time = current_time

    cap.release()
    cv2.destroyAllWindows()

async def websocket_client_func():
    """WebSocket으로 타임스탬프를 수신하고 딕셔너리에 저장하는 스레드"""
    uri = "ws://172.20.10.2:9092" # 타임스탬프 서버의 IP와 포트
    while True:
        try:
            async with websockets.connect(uri) as websocket:
                print("Connected to timestamp server.")
                while True:
                    message_str = await websocket.recv()
                    data = json.loads(message_str)
                    frame_id = data['frame_id']
                    timestamps[frame_id] = data['timestamp']
                    # print(f"Received frame ID_ws: {frame_id}")
                    # 오래된 타임스탬프 데이터 삭제
                    if len(timestamps) > MAX_BUFFER_SIZE:
                        oldest_key = min(timestamps.keys())
                        del timestamps[oldest_key]
        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, asyncio.TimeoutError, json.JSONDecodeError) as e:
            print(f"WebSocket error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)


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

    # 3. 메인 스레드에서 프로그램이 종료되지 않도록 대기
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
