# 비동기 처리를 위해 eventlet 패치
import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template
from flask_socketio import SocketIO
import roslibpy
import threading
import logging
import math

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s')

# --- Flask 및 SocketIO 앱 초기화 ---
app = Flask(__name__)
# secret_key는 SocketIO에 필요할 수 있습니다.
app.config['SECRET_KEY'] = 'secret!'
# 모든 출처에서의 연결을 허용합니다 (개발용).
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# 로봇의 현재 상태를 저장할 전역 변수 (상태 저장소)
robot_status = {
    "pi_cv": { "connected": False, "status": "연결 안됨" },
    "pi_slam": { "rosbridge_connected": False, "last_odom": { "x": 0.0, "y": 0.0, "theta": 0.0 }, "battery":{"percentage":"N/A", "voltage":"N/A"} }
}

# --- ROSBridge 클라이언트 스레드 ---
class RosBridgeClientThread(threading.Thread):
    def __init__(self, socketio_instance):
        super().__init__()
        self.daemon = True # 메인 스레드 종료 시 함께 종료
        self.socketio = socketio_instance
        self.ros_client = None
        self.is_running = True # 스레드의 실행 상태를 제어하는 플래그를 초기화합니다.

        self.ros_host = '172.20.10.10'
        self.ros_port = 9090

    def run(self):
        """ ‼️ 수정된 부분: 재연결을 위한 무한 루프 """
        logging.info("[ROS Thread] ROS 클라이언트 스레드를 시작합니다.")
        while self.is_running:
            try:
                # --- 매 시도마다 새로운 클라이언트 객체 생성 ---
                logging.info("[ROS Thread] 새로운 ROS 클라이언트 객체를 생성하고 연결을 시도합니다.")
                self.ros_client = roslibpy.Ros(host=self.ros_host, port=self.ros_port)

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
                logging.error(f"[ROS Thread] ROS 클라이언트 루프에서 예외 발생: {e}")

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
        logging.info("'/cmd_vel' 토픽 퍼블리셔 생성 완료.")

    def drive_robot(self, direction):
        if not self.is_connected or not self.cmd_vel_publisher:
            logging.warning("ROS가 연결되지 않았거나 퍼블리셔가 준비되지 않았습니다.")
            return

        # 속도 값 설정
        linear_speed = 0.15  # m/s
        angular_speed = 0.5  # rad/s

        twist_msg = {'linear': {'x': 0.0, 'y': 0.0, 'z': 0.0}, 'angular': {'x': 0.0, 'y': 0.0, 'z': 0.0}}

        if direction == 'forward':
            twist_msg['linear']['x'] = linear_speed
        elif direction == 'backward':
            twist_msg['linear']['x'] = -linear_speed
        elif direction == 'left':
            twist_msg['angular']['z'] = angular_speed
        elif direction == 'right':
            twist_msg['angular']['z'] = -angular_speed
        # 'stop'의 경우 모든 값이 0이므로 기본값을 그대로 사용

        logging.info(f"로봇 제어 명령 발행: {direction}")
        self.cmd_vel_publisher.publish(roslibpy.Message(twist_msg))

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
                robot_status['pi_slam']['battery']['percentage'] = round(message['percentage'] * 100)
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
        if self.ros_client.is_connected:
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

if __name__ == '__main__':
    # 1. RosBridge 클라이언트 스레드 인스턴스 생성 및 시작
    ros_thread = RosBridgeClientThread(socketio)
    ros_thread.start()

    # 2. Flask-SocketIO 웹 서버 시작
    logging.info('[Web Server] Flask-SocketIO 서버를 시작합니다. http://0.0.0.0:5001 에서 접속하세요.')
    try:
        # use_reloader=False는 백그라운드 스레드가 두 번 실행되는 것을 방지합니다.
        # allow_unsafe_werkzeug=True는 최신 버전의 Flask/Werkzeug에서 필요할 수 있습니다.
        socketio.run(app, host='0.0.0.0', port=5001, use_reloader=False, debug=False)
    finally:
        # 웹 서버가 종료될 때 ROS 스레드도 깔끔하게 종료합니다.
        ros_thread.stop()
        ros_thread.join()
