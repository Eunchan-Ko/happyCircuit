import roslibpy
import threading
import logging
import eventlet
import config
from web.control.robot_controller import SmoothRobotController

class RosBridgeClientThread(threading.Thread):
    def __init__(self, socketio_instance, robot_status):
        super().__init__()
        self.daemon = True
        self.socketio = socketio_instance
        self.robot_status = robot_status
        self.ros_client = None
        self.is_running = True

        self.ros_host = config.ROS_WEBSOCKET_HOST
        self.ros_port = config.ROS_WEBSOCKET_PORT
        self.robot_controller = None
        self.cmd_vel_publisher = None

    def run(self):
        logging.info("[ROS Thread] ROS 클라이언트 스레드를 시작합니다.")
        while self.is_running:
            try:
                logging.info("[ROS Thread] 새로운 ROS 클라이언트 객체를 생성하고 연결을 시도합니다.")
                self.ros_client = roslibpy.Ros(host=self.ros_host, port=self.ros_port)
                self.ros_client.on_ready(self.on_connect)
                self.ros_client.on('close', self.on_close_handler)
                self.ros_client.on('error', self.on_error_handler)

                logging.info(f"[ROS Thread] rosbridge({self.ros_host}:{self.ros_port})에 연결을 시도합니다...")
                self.ros_client.run_forever()
                logging.info("[ROS Thread] run_forever()가 종료되었습니다.")

            except Exception as e:
                logging.info(f"[ROS Thread] ROS 브릿지 연결에 실패했습니다. error: {e}")

            self.update_status_on_disconnect()

            if self.is_running:
                logging.warning("[ROS Thread] 연결이 끊어졌거나 실패했습니다. 5초 후 재시도합니다.")
                eventlet.sleep(5)

    def on_connect(self):
        logging.info("========================================================")
        logging.info("[ROS Thread] >>> rosbridge 연결 성공! 토픽 구독을 시작합니다. <<<")
        logging.info("========================================================")
        self.robot_status['pi_slam']['rosbridge_connected'] = True
        self.update_web_clients()

        # Odometry 토픽 구독 추가
        odom_listener = roslibpy.Topic(self.ros_client, '/odom', 'nav_msgs/Odometry')
        odom_listener.subscribe(self.odom_callback)
        logging.info("[ROS Thread] '/odom' 토픽 구독 설정 완료.")

        # 배터리 상태 토픽 구독
        battery_listener = roslibpy.Topic(self.ros_client, '/battery_state', 'sensor_msgs/BatteryState')
        battery_listener.subscribe(self.battery_callback)
        logging.info("[ROS Thread] '/battery_state' 토픽 구독 설정 완료.")

        # 지도 토픽 구독
        map_listener = roslibpy.Topic(self.ros_client, '/map', 'nav_msgs/OccupancyGrid')
        map_listener.subscribe(self.map_callback)
        logging.info("[ROS Thread] '/map' 토픽 구독 설정 완료.")

        # 제어를 위한 퍼블리셔 생성
        self.cmd_vel_publisher = roslibpy.Topic(self.ros_client, '/cmd_vel', 'geometry_msgs/Twist')
        logging.info("[ROS Thread]'/cmd_vel' 토픽 퍼블리셔 생성 완료.")

        # 제어를 위한 컨트롤러 생성 (활성화는 app.py에서 제어)
        if self.robot_controller:
            self.robot_controller.shutdown()
        logging.info("[ROS Thread] SmoothRobotController를 생성합니다 (아직 비활성 상태).")
        self.robot_controller = SmoothRobotController(self.cmd_vel_publisher)

    def odom_callback(self, message):
        """/odom 토픽에서 메시지를 수신할 때마다 호출됩니다."""
        try:
            pos = message['pose']['pose']['position']
            orient = message['pose']['pose']['orientation'] # Quaternion

            # Quaternion to Euler (Yaw)
            import math
            x, y, z, w = orient['x'], orient['y'], orient['z'], orient['w']
            t3 = +2.0 * (w * z + x * y)
            t4 = +1.0 - 2.0 * (y * y + z * z)
            yaw_z = math.atan2(t3, t4)

            self.robot_status['pi_slam']['last_odom']['x'] = round(pos['x'], 3)
            self.robot_status['pi_slam']['last_odom']['y'] = round(pos['y'], 3)
            self.robot_status['pi_slam']['last_odom']['theta'] = round(math.degrees(yaw_z), 2)

            self.update_web_clients()
        except KeyError as e:
            logging.warning(f"[ROS Thread] 수신한 odom 메시지에 예상 키가 없습니다: {e}")
        except Exception as e:
            logging.error(f"[ROS Thread] odom_callback에서 에러: {e}")

    def battery_callback(self, message):
        try:
            if 'percentage' in message:
                self.robot_status['pi_slam']['battery']['percentage'] = round(message['percentage'], 1)
            if 'voltage' in message:
                self.robot_status['pi_slam']['battery']['voltage'] = round(message['voltage'], 2)
            self.update_web_clients()
        except Exception as e:
            logging.error(f"Battery callback error: {e}")

    def map_callback(self, message):
        try:
            info = message['info']
            data = message['data']
            map_data = {
                'width': info['width'],
                'height': info['height'],
                'resolution': info['resolution'],
                'origin': {
                    'x': info['origin']['position']['x'],
                    'y': info['origin']['position']['y']
                },
                'data': data
            }
            self.socketio.emit('map_update', map_data)
        except KeyError as e:
            logging.warning(f"[ROS Thread] 수신한 map 메시지에 예상 키가 없습니다: {e}")
        except Exception as e:
            logging.error(f"[ROS Thread] map_callback에서 에러: {e}")

    def on_close_handler(self, proto=None):
        logging.warning("[ROS Thread] roslibpy가 'close' 이벤트를 감지했습니다.")
        self.update_status_on_disconnect()
        if self.ros_client:
            self.ros_client.terminate()

    def on_error_handler(self, error):
        logging.error(f"[ROS Thread] roslibpy가 'error' 이벤트를 감지했습니다: {error}")

    def update_status_on_disconnect(self):
        if self.robot_status['pi_slam']['rosbridge_connected']:
            logging.info("[ROS Thread] 연결 끊김 상태로 전환합니다.")
            self.robot_status['pi_slam']['rosbridge_connected'] = False
            self.robot_status['pi_slam']['last_odom'] = {"x": "N/A", "y": "N/A", "theta": "N/A"}
            self.robot_status['pi_slam']['battery'] = {"percentage": "N/A", "voltage": "N/A"}
            self.update_web_clients()

    def update_web_clients(self):
        self.socketio.emit('status_update', self.robot_status)

    def stop(self):
        self.is_running = False
        if self.robot_controller:
            self.robot_controller.shutdown()
        if self.ros_client and self.ros_client.is_connected:
            self.ros_client.terminate()
        logging.info("[ROS Thread] ROS 클라이언트 스레드를 중지합니다.")

    def activate_controller(self):
        if self.robot_controller:
            self.robot_controller.activate()

    def deactivate_controller(self):
        if self.robot_controller:
            self.robot_controller.deactivate()
