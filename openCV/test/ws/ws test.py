# mac_ws_client.py (새 파일)
import asyncio
import websockets
import cv2
import numpy as np
import base64
import time
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import csv

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

    plt.title("FPS and Bandwidth Over Time")
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax2.legend(lines + lines2, labels + labels2, loc='upper left')

    fig.tight_layout()
    plt.savefig("performance_over_time_ws.png")
    plt.close()
    print("✅ 통합 성능 그래프가 'performance_over_time_ws.png'로 저장되었습니다.")

    # --- 지연 시간 그래프 (Latency) ---
    plt.figure(figsize=(12, 6))
    plt.plot(times, latency_values, color='tab:green', label='Avg Latency (ms)')
    plt.xlabel("Time (seconds)")
    plt.ylabel("Avg Latency (ms)")
    plt.title("Average Latency Over Time")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    plt.savefig("latency_over_time_ws.png")
    plt.close()
    print("✅ 평균 지연 시간 그래프가 'latency_over_time_ws.png'로 저장되었습니다.")

def save_csv(data_points):
    """수집된 데이터를 CSV 파일로 저장합니다."""
    if not data_points:
        print("데이터 포인트가 없어 CSV 파일을 생성할 수 없습니다.")
        return
    
    keys = data_points[0].keys()
    with open('streaming_data.csv', 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(data_points)
    print("✅ 데이터가 'streaming_data.csv'로 저장되었습니다.")

def save_report(data_points):
    """그래프와 CSV를 저장하는 리포트 생성 함수"""
    print("\n" + "="*50)
    print("데이터 수집 완료. 리포트를 생성합니다...")
    print("="*50)

    if not data_points:
        print("수집된 데이터가 없어 리포트를 생성할 수 없습니다.")
        print("스트림이 정상적으로 시작되었는지, 1초 이상 실행되었는지 확인해주세요.")
        print("="*50 + "\n")
        return

    save_graphs(data_points)
    save_csv(data_points)
    print("="*50)
    print("모든 리포트 생성이 완료되었습니다.")
    print("="*50 + "\n")

async def receive_stream():
    uri = "ws://172.20.10.2:9091" # 라즈베리파이 IP 주소 입력
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Connected to {uri}")

            # ... (이하 변수 초기화 코드는 동일)
            frame_count = 0
            total_bytes_in_second = 0
            latencies = []
            proc_times = []
            start_time = time.time()

            COLLECTION_DURATION = 600
            data_points = []
            collection_start_time = time.time()
            is_collecting = True
            print(f"데이터 수집을 {COLLECTION_DURATION}초 동안 시작합니다...")

            while True:
                message_str = await websocket.recv()
                reception_time = time.time()
                
                try:
                    # 데이터 파싱
                    data = json.loads(message_str)
                    send_timestamp = data['timestamp']
                    img_b64 = data['image']
                except (KeyError, json.JSONDecodeError) as e:
                    print("--- 데이터 파싱 에러 ---")
                    print(f"에러 타입: {type(e).__name__}")
                    print("에러 내용: ", e)
                    print("수신된 메시지 원본 (첫 500자):")
                    print(message_str[:500])
                    print("-------------------------")
                    # 에러 발생 시 루프를 중단하고 최종 리포트 생성 시도
                    raise

                total_bytes_in_second += len(message_str)
                
                # 1. 전송 지연 시간 (Latency) 계산
                latency = (reception_time - send_timestamp) * 1000
                latencies.append(latency)

                # ... (이하 로직은 동일)
                img_bytes = base64.b64decode(img_b64)
                proc_start_time = time.time()
                np_arr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                blurred_frame = cv2.GaussianBlur(gray_frame, (5, 5), 0)
                proc_end_time = time.time()
                processing_time = (proc_end_time - proc_start_time) * 1000
                proc_times.append(processing_time)

                frame_count += 1
                
                current_time = time.time()
                elapsed_time = current_time - start_time
                if elapsed_time >= 1.0:
                    fps = frame_count / elapsed_time
                    bandwidth_kbps = (total_bytes_in_second * 8) / (elapsed_time * 1024)
                    avg_latency = np.mean(latencies) if latencies else 0
                    avg_proc_time = np.mean(proc_times) if proc_times else 0

                    print(f"FPS: {fps:.2f}, Bandwidth: {bandwidth_kbps:.2f} kbps, Avg Latency: {avg_latency:.2f} ms, Avg Proc Time: {avg_proc_time:.2f} ms")

                    if is_collecting:
                        collection_elapsed_time = current_time - collection_start_time
                        data_points.append({
                            'time': round(collection_elapsed_time, 2),
                            'fps': round(fps, 2),
                            'bandwidth': round(bandwidth_kbps, 2),
                            'avg_latency_ms': round(avg_latency, 2),
                            'avg_proc_time_ms': round(avg_proc_time, 2)
                        })

                        if collection_elapsed_time >= COLLECTION_DURATION:
                            is_collecting = False
                            if len(data_points) > 1:
                                save_report(data_points[1:])
                            else:
                                print("수집된 데이터가 부족하여 리포트를 생성할 수 없습니다.")
                            print("데이터 수집이 완료되었습니다. 프로그램을 종료합니다.")
                            break

                    frame_count = 0
                    total_bytes_in_second = 0
                    latencies = []
                    proc_times = []
                    start_time = current_time

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {e}")
    except Exception as e:
        # 위에서 처리되지 않은 다른 예외들
        print(f"An unexpected error occurred: {e}")
    finally:
        if is_collecting and len(data_points) > 1:
            print("\n스트림이 비정상적으로 종료되었습니다. 현재까지 수집된 데이터로 리포트를 생성합니다.")
            save_report(data_points[1:])

if __name__ == "__main__":
    try:
        asyncio.run(receive_stream())
    except KeyboardInterrupt:
        print("\nClient stopped by user.")