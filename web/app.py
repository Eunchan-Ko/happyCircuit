# 비동기 처리를 위해 eventlet 패치
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO
from control.routes import control_bp
from disconnection_check.routes import disconnection_check_bp
from control.robot_controller import SmoothRobotController
import roslibpy
import threading
import logging
import math
import websocket
import base64
import atexit

# --- 설정 파일 로드 ---
import config

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')

# --- Flask 및 SocketIO 앱 초기화 ---
app = Flask(__name__)
# --- Flask 앱에 /control 루트 추가 ---
app.register_blueprint(control_bp)
app.register_blueprint(disconnection_check_bp)
# secret_key는 SocketIO에 필요할 수 있습니다.
app.config['SECRET_KEY'] = 'secret!'
# 모든 출처에서의 연결을 허용합니다 (개발용).
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 로봇의 현재 상태를 저장할 전역 변수 (상태 저장소)
robot_status = {
    "pi_cv": { "connected": False, "status": "연결 안됨" },
    "pi_slam": { "rosbridge_connected": False, "last_odom": { "x": 0.0, "y": 0.0, "theta": 0.0 }, "battery":{"percentage":"N/A", "voltage":"N/A"} }
}

# --- Image 클라이언트 스레드 ---
class ImageClientThread(threading.Thread):
    def __init__(self, socketio_instance):
        super().__init__()
        self.daemon = True
        self.socketio = socketio_instance
        self.is_running = True
        self.ws = None
        self.host = config.PI_CV_WEBSOCKET_HOST
        self.port = config.PI_CV_WEBSOCKET_PORT

    def run(self):
        logging.info("[Image Thread] 이미지 클라이언트 스레드를 시작합니다.")
        while self.is_running:
            try:
                logging.info("[Image Thread] 새로운 ROS 클라이언트 객체를 생성하고 연결을 시도합니다.")
                self.ws = websocket.create_connection(f"ws://{self.host}:{self.port}")
                robot_status['pi_cv']['connected'] = True
                robot_status['pi_cv']['status'] = "연결됨"
                self.socketio.emit('status_update', robot_status)
                logging.info(f"[Image Thread] 이미지 서버 ({self.host}:{self.port})에 연결되었습니다.")
                while self.is_running:
                    try:
                        message = self.ws.recv()
                        self.socketio.emit('new_image', {'image': message})
                    except websocket.WebSocketConnectionClosedException:
                        logging.warning("[Image Thread] 이미지 서버와의 연결이 끊어졌습니다.")
                        break
            except Exception as e:
                logging.warning(f"[Image Thread] 이미지 서버에 연결할 수 없습니다.")

            robot_status['pi_cv']['connected'] = False
            robot_status['pi_cv']['status'] = "연결 안됨"
            self.socketio.emit('status_update', robot_status)
            
            if self.is_running:
                logging.info("[Image Thread] 5초 후 재연결을 시도합니다.")
                eventlet.sleep(5)

    def stop(self):
        self.is_running = False
        if self.ws:
            self.ws.close()
        logging.info("[Image Thread] 이미지 클라이언트 스레드를 중지합니다.")

# --- ROSBridge 클라이언트 스레드 ---
class RosBridgeClientThread(threading.Thread):
    def __init__(self, socketio_instance):
        super().__init__()
        self.daemon = True # 메인 스레드 종료 시 함께 종료
        self.socketio = socketio_instance
        self.ros_client = None
        self.is_running = True # 스레드의 실행 상태를 제어하는 플래그를 초기화합니다.

        self.ros_host = config.ROS_WEBSOCKET_HOST
        self.ros_port = config.ROS_WEBSOCKET_PORT
        # robot controll attribute 등록
        self.robot_controller = None
        self.cmd_vel_publisher = None
    def run(self):
        """ ‼️ 수정된 부분: 재연결을 위한 무한 루프 """
        logging.info("[ROS Thread] ROS 클라이언트 스레드를 시작합니다.")
        while self.is_running:
            try:
                # --- 매 시도마다 새로운 클라이언트 객체 생성 ---
                logging.info("[ROS Thread] 새로운 ROS 클라이언트 객체를 생성하고 연결을 시도합니다.")
                self.ros_client = roslibpy.Ros(host=self.ros_host, port=self.ros_port, install_signal_handlers=False)

                # --- 새로운 객체에 이벤트 핸들러 등록 ---
                self.ros_client.on_ready(self.on_connect)
                self.ros_client.on('close', self.on_close_handler)
                self.ros_client.on('error', self.on_error_handler)

                logging.info(f"[ROS Thread] rosbridge({self.ros_host}:{self.ros_port})에 연결을 시도합니다...")
                # run_forever()는 연결이 끊어질 때까지 여기서 실행을 멈춥니다.
                self.ros_client.run_forever()

                # run_forever()가 정상적으로 종료된 경우 (예: terminate() 호출)
                logging.info("[ROS Thread] run_forever()가 종료되었습니다.")

            except Exception as e:
                logging.info(f"[ROS Thread] ROS 브릿지 연결에 실패했습니다.")

            # run_forever()가 종료되거나 예외가 발생하면 이 코드가 실행됩니다.
            # 이는 연결이 끊어졌음을 의미합니다.
            self.update_status_on_disconnect()

            if self.is_running:
                logging.warning("[ROS Thread] 연결이 끊어졌거나 실패했습니다. 5초 후 재시도합니다.")
                eventlet.sleep(5)
    """로봇과 정상적으로 websocket이 연결됐을 때 실행됌."""
    def on_connect(self):
        """rosbridge에 성공적으로 연결되었을 때 호출됩니다."""
        logging.info("==========================================================")
        logging.info("[ROS Thread] >>> rosbridge 연결 성공! 토픽 구독을 시작합니다. <<<")
        logging.info("==========================================================")
        robot_status['pi_slam']['rosbridge_connected'] = True
        self.update_web_clients()

        # Odometry 토픽 구독
        odom_listener = roslibpy.Topic(self.ros_client, '/odom', 'nav_msgs/Odometry')
        odom_listener.subscribe(self.odom_callback)
        logging.info("[ROS Thread] '/odom' 토픽 구독 설정 완료.")

        # 배터리 상태 토픽 구독
        battery_listener = roslibpy.Topic(self.ros_client, '/battery_state', 'sensor_msgs/BatteryState')
        battery_listener.subscribe(self.battery_callback)
        logging.info("[ROS Thread] '/battery_state' 토픽 구독 설정 완료.")

        # ✅ 제어를 위한 퍼블리셔 생성
        self.cmd_vel_publisher = roslibpy.Topic(
            self.ros_client,
            '/cmd_vel',                 # 토픽 이름
            'geometry_msgs/Twist'       # 메시지 타입
        )
        logging.info("[ROS Thread]'/cmd_vel' 토픽 퍼블리셔 생성 완료.")

        # 제어를 위한 컨트롤러 생성
        if self.robot_controller:
            self.robot_controller.stop()
        logging.info("[ROS Thread] SmoothRobotController를 생성하고 시작합니다.")
        self.robot_controller = SmoothRobotController(self.cmd_vel_publisher)
        self.robot_controller.start()

    def odom_callback(self, message):
        """/odom 토픽에서 메시지를 수신할 때마다 호출됩니다."""
        #logging.info("[ROS Thread] /odom 메시지 수신!") # <-- 데이터 수신 확인용 로그 추가
        try:
            pos = message['pose']['pose']['position']
            orient = message['pose']['pose']['orientation'] # Quaternion

            # Quaternion to Euler (Yaw)
            # ROS의 Z축 회전(yaw)을 계산합니다.
            import math
            x, y, z, w = orient['x'], orient['y'], orient['z'], orient['w']
            t3 = +2.0 * (w * z + x * y)
            t4 = +1.0 - 2.0 * (y * y + z * z)
            yaw_z = math.atan2(t3, t4)

            robot_status['pi_slam']['last_odom']['x'] = round(pos['x'], 3)
            robot_status['pi_slam']['last_odom']['y'] = round(pos['y'], 3)
            robot_status['pi_slam']['last_odom']['theta'] = round(math.degrees(yaw_z), 2) # 라디안을 각도로 변환

            # 데이터 수신 후 웹 클라이언트에 즉시 전송
            self.update_web_clients()
        except KeyError as e:
            logging.warning(f"[ROS Thread] 수신한 odom 메시지에 예상 키가 없습니다: {e}")
        except Exception as e:
            logging.error(f"[ROS Thread] odom_callback에서 에러: {e}")

    def battery_callback(self, message):
        """/battery_state 메시지 수신 시 호출"""
        try:
            if 'percentage' in message:
                robot_status['pi_slam']['battery']['percentage'] = round(message['percentage'],1)
            if 'voltage' in message:
                robot_status['pi_slam']['battery']['voltage'] = round(message['voltage'], 2)
            self.update_web_clients()
        except Exception as e:
            logging.error(f"Battery callback error: {e}")
    def on_close_handler(self, proto=None):
        """roslibpy가 'close' 이벤트를 감지했을 때 호출될 콜백"""
        logging.warning("[ROS Thread] roslibpy가 'close' 이벤트를 감지했습니다.")

    def on_error_handler(self, error):
        """roslibpy가 'error' 이벤트를 감지했을 때 호출될 콜백"""
        logging.error(f"[ROS Thread] roslibpy가 'error' 이벤트를 감지했습니다: {error}")

    def update_status_on_disconnect(self):
        """연결이 끊겼을 때 상태를 일관되게 업데이트하는 함수"""
        if robot_status['pi_slam']['rosbridge_connected']:
            logging.info("[ROS Thread] 연결 끊김 상태로 전환합니다.")
            robot_status['pi_slam']['rosbridge_connected'] = False
            robot_status['pi_slam']['last_odom'] = {"x": "N/A", "y": "N/A", "theta": "N/A"}
            robot_status['pi_slam']['battery'] = {"percentage": "N/A", "voltage": "N/A"}
            self.update_web_clients()

    def update_web_clients(self):
        """모든 연결된 웹 클라이언트에게 현재 로봇 상태를 전송합니다."""
        self.socketio.emit('status_update', robot_status)

    def stop(self):
        self.is_running = False
        if self.ros_client and self.ros_client.is_connected:
            self.ros_client.terminate()
        logging.info("[ROS Thread] ROS 클라이언트 스레드를 중지합니다.")

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
    ros_thread = RosBridgeClientThread(socketio)
    ros_thread.start()

    # 2. Image 클라이언트 스레드 인스턴스 생성 및 시작
    image_thread = ImageClientThread(socketio)
    image_thread.start()

    # 3. 프로그램 종료 시 cleanup 함수가 실행되도록 등록
    atexit.register(cleanup)

    # 4. Flask-SocketIO 웹 서버 시작
    logging.info(f'[Web Server] Flask-SocketIO 서버를 시작합니다. http://{config.FLASK_HOST}:{config.FLASK_PORT} 에서 접속하세요.')
    # use_reloader=False는 백그라운드 스레드가 두 번 실행되는 것을 방지합니다.
    # allow_unsafe_werkzeug=True는 최신 버전의 Flask/Werkzeug에서 필요할 수 있습니다.
    socketio.run(app, host=config.FLASK_HOST, port=config.FLASK_PORT, use_reloader=False, debug=False)
