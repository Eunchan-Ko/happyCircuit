import base64
import json
import logging
import threading
import time
import websocket
import numpy as np
import cv2
from ultralytics import YOLO
from datetime import datetime
import os
import eventlet
import torch

import config

from web.config import DB_connect

# --- YOLO 모델 로드 및 설정 ---
if torch.backends.mps.is_available():
    device = torch.device("mps")
    logging.info("[YOLO] Apple Silicon GPU (MPS)를 사용합니다.")
else:
    device = torch.device("cpu")
    logging.info("[YOLO] CPU를 사용합니다.")

try:
    yolo_model = YOLO(config.YOLO_MODEL_PATH)
    yolo_names = yolo_model.names if hasattr(yolo_model, "names") else {}
    damage_class_idxs = []
    if yolo_names:
        iterable = yolo_names.items() if isinstance(yolo_names, dict) else enumerate(yolo_names)
        for idx, name in iterable:
            if any(k in str(name).lower() for k in config.YOLO_DAMAGE_KEYWORDS):
                damage_class_idxs.append(int(idx))
        logging.info(f"[YOLO] '손상' 관련 클래스 인덱스 확인: {damage_class_idxs}")
    logging.info(f"[YOLO] 모델 '{config.YOLO_MODEL_PATH}' 로드 성공")
except Exception as e:
    logging.error(f"[YOLO] 모델 로드 실패: {e}")
    yolo_model = None


class ImageClientThread(threading.Thread):
    def __init__(self, socketio_instance, robot_status, warnings_collection, image_storage_root):
        super().__init__()
        self.daemon = True
        self.socketio = socketio_instance
        self.robot_status = robot_status
        self.warnings_collection = warnings_collection
        self.image_storage_root = image_storage_root
        self.is_running = True
        self.ws = None
        self.host = config.PI_CV_WEBSOCKET_HOST
        self.port = config.PI_CV_WEBSOCKET_PORT

    def run(self):
        # 변수 설정
        frame_counter = 0
        inference_interval = 1
        logging.info("[Image Thread] 이미지 클라이언트 스레드를 시작합니다.")
        while self.is_running:
            try:
                logging.info("[Image Thread] 이미지 서버에 연결을 시도합니다...")
                self.ws = websocket.create_connection(f"ws://{self.host}:{self.port}", timeout=5)
                self.robot_status['pi_cv']['connected'] = True
                self.robot_status['pi_cv']['status'] = "연결됨"
                self.socketio.emit('status_update', self.robot_status)
                logging.info(f"[Image Thread] 이미지 서버 ({self.host}:{self.port})에 연결되었습니다.")

                while self.is_running:
                    try:
                        # 1. 원본 메시지(JSON) 수신
                        raw_message = self.ws.recv()
                        # 2. JSON 파싱하여 이미지 데이터(base64) 추출
                        try:
                            data = json.loads(raw_message)
                            b64_image = data['image']
                        except (json.JSONDecodeError, KeyError) as e:
                            logging.warning(f"[Image Thread] 수신한 데이터가 올바른 JSON 형식이 아닙니다: {e}")
                            continue # 다음 프레임으로 넘어감

                        frame_counter += 1
                        # 3. YOLO 모델이 없으면 원본 이미지만 전송
                        if not yolo_model:
                            self.socketio.emit('new_image', {'image': b64_image})
                            continue

                        # 3. 3프레임마다 이미지 처리 및 YOLO 추론
                        if frame_counter % inference_interval == 0:
                            frame_counter = 0
                            try:
                                # Base64 -> Numpy Array -> OpenCV Image
                                img_bytes = base64.b64decode(b64_image)
                                np_arr = np.frombuffer(img_bytes, np.uint8)
                                cv_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

                                # YOLO 추론 실행
                                # cv_image가 None이 아닌 경우에만 추론을 실행합니다.
                                if cv_image is None:
                                    logging.warning("[Image Thread] 이미지 디코딩 실패, 현재 프레임을 건너뜁니다.")
                                    self.socketio.emit('new_image', {'image': b64_image}) # 원본(아마도 손상된) 이미지를 전송
                                    continue
                                results = yolo_model(cv_image, imgsz=config.YOLO_IMG_SIZE, conf=config.YOLO_CONF_THRES, verbose=False)

                                # 추론 결과(bounding box)를 원본 이미지에 그리기
                                annotated_image = results[0].plot()

                                # 'damage' 클래스 검출 여부 확인
                                damage_detected = False
                                detected_boxes = []
                                # object class 검출시 사진 분석 후 DB 저장
                                for box in results[0].boxes:
                                    # logging.info("[Image Thread] Data Analysising")
                                    if int(box.cls) in damage_class_idxs:
                                        # logging.info("[Image Thread] Damage Detected")
                                        damage_detected = True
                                        detected_boxes.append({
                                            'class_id': int(box.cls),
                                            'class_name': yolo_names.get(int(box.cls), 'Unknown'),
                                            'confidence': float(box.conf),
                                            'box_coords': box.xyxyn.cpu().numpy().tolist() # 정규화된 좌표
                                        })

                                # Bounding Box가 그려진 이미지를 Base64로 인코딩
                                _, buffer = cv2.imencode('.jpg', annotated_image)
                                annotated_b64_image = base64.b64encode(buffer).decode('utf-8')

                                # damage가 검출되면 DB에 저장 (위치 중복 확인 포함)
                                if DB_connect and damage_detected and self.warnings_collection is not None:
                                    logging.info("[Image Thread] warning class를 검출했습니다. DB에 이미지 저장을 시도합니다.")
                                    try:
                                        # 1. 현재 로봇의 odom 데이터 가져오기
                                        current_odom = self.robot_status['pi_slam']['last_odom']
                                        odom_x = current_odom.get('x')
                                        odom_y = current_odom.get('y')

                                        # 2. odom 데이터가 유효한 숫자인지 확인
                                        if isinstance(odom_x, (int, float)) and isinstance(odom_y, (int, float)):
                                            # 3. 현재 위치 근처에 이미 저장된 경고가 있는지 확인 (50cm 반경)
                                            min_distance_meters = 0.5

                                            query = {
                                                "location": {
                                                    "$near": {
                                                        "$geometry": {
                                                            "type": "Point",
                                                            "coordinates": [odom_x, odom_y]
                                                        },
                                                        "$maxDistance": min_distance_meters
                                                    }
                                                }
                                            }
                                            existing_warning = self.warnings_collection.find_one(query)

                                            if existing_warning:
                                                logging.info(f"[DB] 현재 위치 ({odom_x:.2f}, {odom_y:.2f}) 근처에 이미 경고가 저장되어 있어 중복 저장을 건너뜁니다.")
                                            else:
                                                # 4. 중복이 아니면 이미지 파일로 저장하고 DB에는 경로를 저장
                                                timestamp = datetime.utcnow()
                                                ts_str = timestamp.strftime('%Y%m%d_%H%M%S_%f')
                                                class_names = '-'.join(sorted(list(set(d['class_name'] for d in detected_boxes)))) or 'detection'
                                                filename = f"{ts_str}_{class_names}.jpg"

                                                # web/static/imgs/line_crash/filename.jpg
                                                absolute_path = os.path.join(self.image_storage_root, filename)

                                                # 이미지 파일 저장
                                                cv2.imwrite(absolute_path, annotated_image)

                                                # DB에 저장할 문서
                                                doc = {
                                                    "timestamp": timestamp,
                                                    "odom": current_odom,
                                                    "location": {"type": "Point", "coordinates": [odom_x, odom_y]},
                                                    "detections": detected_boxes,
                                                    "image_path": os.path.join('imgs', 'line_crash', filename) # 웹에서 접근할 경로
                                                }
                                                self.warnings_collection.insert_one(doc)
                                                logging.info(f"[DB] 손상 감지: 새로운 위치({odom_x:.2f}, {odom_y:.2f})의 경고를 DB에 저장했습니다 (이미지: {filename}).")
                                        else:
                                            # odom 데이터가 유효하지 않을 경우, 시간 기반으로 중복 저장 방지
                                            na_save_interval_seconds = 10 # 최소 저장 간격 (초)

                                            # 'location' 필드가 없는 가장 최근 문서를 찾음
                                            last_na_warning = self.warnings_collection.find_one(
                                                {"odom.x": "N/A"},
                                                sort=[('timestamp', -1)]
                                            )

                                            should_save = True
                                            if last_na_warning:
                                                time_since_last = datetime.utcnow() - last_na_warning['timestamp']
                                                if time_since_last.total_seconds() < na_save_interval_seconds:
                                                    should_save = False
                                                    logging.info(f"[DB] Odom N/A 상태. 마지막 저장 후 {time_since_last.total_seconds():.1f}초 경과. {na_save_interval_seconds}초 내 중복 저장을 방지합니다.")

                                            if should_save:
                                                logging.warning("[DB] Odom 데이터가 유효하지 않아 시간 간격에 따라 경고를 저장합니다.")

                                                # 이미지 파일로 저장하고 DB에는 경로를 저장
                                                timestamp = datetime.utcnow()
                                                ts_str = timestamp.strftime('%Y%m%d_%H%M%S_%f')
                                                class_names = '-'.join(sorted(list(set(d['class_name'] for d in detected_boxes)))) or 'detection'
                                                filename = f"{ts_str}_{class_names}.jpg"

                                                absolute_path = os.path.join(self.image_storage_root, filename)

                                                # 이미지 파일 저장
                                                cv2.imwrite(absolute_path, annotated_image)

                                                # DB에 저장할 문서
                                                doc = {
                                                    "timestamp": timestamp,
                                                    "odom": current_odom, # "N/A" 등 비정상 데이터라도 일단 기록
                                                    "detections": detected_boxes,
                                                    "image_path": os.path.join('imgs', 'line_crash', filename) # 웹에서 접근할 경로
                                                }
                                                self.warnings_collection.insert_one(doc)
                                                logging.info(f"[DB] Odom N/A. 경고를 DB에 저장했습니다 (이미지: {filename}).")

                                    except Exception as e:
                                        logging.error(f"[DB] 경고 데이터를 MongoDB에 저장하는 중 오류 발생: {e}")

                                # 상태가 변경되었을 때만 업데이트 및 전송
                                if self.robot_status['pi_cv']['damage_detected'] != damage_detected:
                                    self.robot_status['pi_cv']['damage_detected'] = damage_detected
                                    self.socketio.emit('status_update', self.robot_status)

                                # Bounding Box가 그려진 이미지를 Base64로 인코딩하여 전송
                                self.socketio.emit('new_image', {'image': annotated_b64_image})

                            except Exception as e:
                                logging.error(f"[Image Thread] 이미지 처리 중 오류 발생: {e}")
                                # 오류 발생 시 원본 이미지라도 전송하여 스트림이 끊기지 않도록 함
                                self.socketio.emit('new_image', {'image': b64_image})
                        else:
                            self.socketio.emit('new_image', {'image': b64_image})
                    except websocket.WebSocketTimeoutException:
                        logging.warning("[Image Thread] 이미지 서버로부터 데이터 수신 시간 초과. 연결을 재설정합니다.")
                        break
                    except websocket.WebSocketConnectionClosedException:
                        logging.warning("[Image Thread] 이미지 서버와의 연결이 끊어졌습니다.")
                        break # 내부 루프를 빠져나가 재연결 로직으로 이동

            except Exception as e:
                logging.warning(f"[Image Thread] 이미지 서버에 연결할 수 없습니다: {e}")

            # 연결이 끊겼거나, 연결에 실패했을 경우 상태 업데이트
            self.robot_status['pi_cv']['connected'] = False
            self.robot_status['pi_cv']['status'] = "연결 안됨"
            self.robot_status['pi_cv']['damage_detected'] = None # 연결 끊김 시 None으로 초기화
            logging.info("[Image Thread] 클라이언트에 연결 끊김 상태 전송.")
            self.socketio.emit('status_update', self.robot_status)

            if self.is_running:
                logging.info("[Image Thread] 5초 후 재연결을 시도합니다.")
                eventlet.sleep(5)

    def stop(self):
        self.is_running = False
        if self.ws:
            self.ws.close()
        logging.info("[Image Thread] 이미지 클라이언트 스레드를 중지합니다.")