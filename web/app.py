import sys
import os

# 프로젝트 루트 디렉토리를 Python 경로에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- 설정 파일 로드 ---
import config

# 비동기 처리를 위해 eventlet 패치
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO
from web.control.routes import control_bp
from web.disconnection_check.routes import disconnection_check_bp

import logging
import atexit

# --- 추가된 라이브러리 ---
from web.threads.image_client import ImageClientThread
from web.threads.rosbridge_client import RosBridgeClientThread


# --- 이미지 저장 경로 설정 ---
IMAGE_STORAGE_ROOT = os.path.join(os.path.dirname(__file__), 'static', 'imgs', 'line_crash')
os.makedirs(IMAGE_STORAGE_ROOT, exist_ok=True)
logging.info(f"[File] 이미지 저장 경로 확인: {IMAGE_STORAGE_ROOT}")


# --- Flask 및 SocketIO 앱 초기화 ---
app = Flask(__name__)
# --- Flask 앱에 /control 루트 추가 ---
app.register_blueprint(control_bp)
app.register_blueprint(disconnection_check_bp)
app.register_blueprint(map_bp)
# secret_key는 SocketIO에 필요할 수 있습니다.
app.config['SECRET_KEY'] = 'secret!'
# 모든 출처에서의 연결을 허용합니다 (개발용).
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- MongoDB 설정 ---
try:
    # config.py에 정의된 MONGODB_CLIENT를 사용
    mongo_client = config.MONGODB_CLIENT
    db = mongo_client.happy_circuit_db # 데이터베이스 선택
    warnings_collection = db.warnings # 컬렉션 선택
    # 위치 기반 중복 저장을 방지하기 위해 2dsphere 인덱스 생성
    warnings_collection.create_index([("location", "2dsphere")])
    logging.info("[DB] MongoDB에 성공적으로 연결 및 'warnings' 컬렉션과 인덱스 준비 완료.")
except AttributeError:
    logging.error("[DB] 'config.py'에 'MONGODB_CLIENT'가 정의되지 않았습니다. DB 관련 기능이 비활성화됩니다.")
    warnings_collection = None
except Exception as e:
    logging.error(f"[DB] MongoDB 연결 또는 설정 실패: {e}")
    warnings_collection = None


# 로봇의 현재 상태를 저장할 전역 변수 (상태 저장소)
robot_status = {
    "pi_cv": { "connected": False, "status": "연결 안됨", "damage_detected": None }, # YOLO 결과 저장을 위해 damage_detected 추가
    "pi_slam": { "rosbridge_connected": False, "last_odom": { "x": "N/A", "y": "N/A", "theta": "N/A" }, "battery":{"percentage":"N/A", "voltage":"N/A"} }
}


# --- Flask 라우트 및 SocketIO 이벤트 핸들러 ---
@app.route('/')
def index():
    # index.html을 렌더링합니다.
    return render_template('index.html')

# 웹 클라이언트가 처음 연결되었을 때 호출됩니다.
@socketio.on('connect')
def handle_web_client_connect():
    logging.info(f"[Web Server] 클라이언트 연결됨. 현재 상태 전송.")
    # 연결된 클라이언트에게 현재 로봇 상태를 즉시 전송해줍니다.
    socketio.emit('status_update', robot_status)

# 웹 클라이언트가 연결이 끊어졌을 때 호출됩니다.
@socketio.on('disconnect')
def handle_web_client_disconnect():
    """웹 클라이언트의 연결이 끊어졌을 때 호출됩니다."""
    logging.info("[Web Server] 클라이언트 연결 끊어짐")

# 웹 클라이언트에서 drive 명령을 입력했을 때 호출됩니다.
@socketio.on('drive_command')
def handle_drive_command(data):
    direction = data.get('direction')
    # 컨트롤러가 생성되었고(즉, ROS가 연결됨), 방향 값이 있을 때만 실행
    if ros_thread.robot_controller and direction:
        ros_thread.robot_controller.set_direction(direction)
        logging.info(f"[Web Server] 로봇 컨트롤중 (direction: \"{direction}\")")
    elif not ros_thread.robot_controller:
        logging.warning("[Web Server] 로봇 컨트롤러가 준비되지 않아 drive_command를 무시합니다.")

# --- 프로그램 종료 시 실행될 정리(cleanup) 함수 ---
def cleanup():
    logging.info("프로그램 종료 시작...")
    # 1. ROS 스레드 종료
    if 'ros_thread' in globals() and ros_thread.is_alive():
        logging.info("ROS 스레드 종료 중...")
        ros_thread.stop()
        ros_thread.join() # 스레드가 완전히 끝날 때까지 대기
    
    # 2. 이미지 스레드 종료
    if 'image_thread' in globals() and image_thread.is_alive():
        logging.info("이미지 스레드 종료 중...")
        image_thread.stop()
        image_thread.join() # 스레드가 완전히 끝날 때까지 대기

    logging.info("모든 스레드가 성공적으로 종료되었습니다. 프로그램을 완전히 종료합니다.")

if __name__ == '__main__':
    # 1. RosBridge 클라이언트 스레드 인스턴스 생성 및 시작
    ros_thread = RosBridgeClientThread(socketio, robot_status)
    ros_thread.start()

    # 2. Image 클라이언트 스레드 인스턴스 생성 및 시작
    image_thread = ImageClientThread(socketio, robot_status, warnings_collection, IMAGE_STORAGE_ROOT)
    image_thread.start()

    # 3. 프로그램 종료 시 cleanup 함수가 실행되도록 등록
    atexit.register(cleanup)

    # 4. Flask-SocketIO 웹 서버 시작
    logging.info(f'[Web Server] Flask-SocketIO 서버를 시작합니다. http://{config.FLASK_HOST}:{config.FLASK_PORT} 에서 접속하세요.')
    # use_reloader=False는 백그라운드 스레드가 두 번 실행되는 것을 방지합니다.
    # allow_unsafe_werkzeug=True는 최신 버전의 Flask/Werkzeug에서 필요할 수 있습니다.
    socketio.run(app, host=config.FLASK_HOST, port=config.FLASK_PORT, use_reloader=False, debug=False)
