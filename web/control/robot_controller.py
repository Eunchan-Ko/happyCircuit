import time
import threading
import roslibpy
import logging

class SmoothRobotController:
    """
    로봇의 주행을 부드럽게 가속/감속하며 제어하는 클래스.
    백그라운드 스레드에서 주기적으로 속도를 업데이트합니다.
    """
    def __init__(self, publisher):
        if not publisher:
            raise ValueError("Publisher는 필수입니다.")
        self.publisher = publisher

        # --- 제어 파라미터 (이 값들을 조절하여 움직임을 튜닝) ---
        self.max_linear_speed = 0.22  # 최대 직진 속도 (m/s)
        self.max_angular_speed = 3.0  # 최대 회전 속도 (rad/s)
        self.acceleration = 0.02      # 초당 가속도 (값이 클수록 빨리 가속)
        self.deceleration = 0.15      # 초당 감속도 (값이 클수록 빨리 감속, 보통 가속보다 빠르게 설정)
        self.update_rate = 20         # 1초에 몇 번 명령을 보낼지 (Hz)
        # ---------------------------------------------------------

        # 상태 변수
        self.target_linear_speed = 0.0
        self.target_angular_speed = 0.0
        self.current_linear_speed = 0.0
        self.current_angular_speed = 0.0

        # 백그라운드 스레드 설정
        self._shutdown_event = threading.Event()
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)

    def set_direction(self, direction):
        """
        프론트엔드로부터 방향 명령을 받아 목표 속도를 설정합니다.
        'stop' 명령은 즉시 목표 속도를 0으로 만들어 빠른 정지를 유도합니다.
        """
        logging.info(f"[Controller] 방향 설정: {direction}")
        if direction == 'forward':
            self.target_linear_speed = self.max_linear_speed
            self.target_angular_speed = 0.0
        elif direction == 'backward':
            self.target_linear_speed = -self.max_linear_speed
            self.target_angular_speed = 0.0
        elif direction == 'left':
            self.target_angular_speed = self.max_angular_speed
            self.target_linear_speed = 0.0
        elif direction == 'right':
            self.target_angular_speed = -self.max_angular_speed
            self.target_linear_speed = 0.0
        elif direction == 'stop':
            self.target_linear_speed = 0.0
            self.target_angular_speed = 0.0

    def _update_loop(self):
        """백그라운드에서 실행되며 현재 속도를 목표 속도까지 점진적으로 변경하고 ROS 토픽을 발행합니다."""
        logging.info("로봇 제어 루프 시작.")
        while not self._shutdown_event.is_set():
            # 선형 속도 업데이트
            if self.current_linear_speed < self.target_linear_speed:
                self.current_linear_speed = min(self.target_linear_speed, self.current_linear_speed + self.acceleration)
            elif self.current_linear_speed > self.target_linear_speed:
                self.current_linear_speed = max(self.target_linear_speed, self.current_linear_speed - self.deceleration)

            # 각속도 업데이트
            if self.current_angular_speed < self.target_angular_speed:
                self.current_angular_speed = min(self.target_angular_speed, self.current_angular_speed + self.acceleration)
            elif self.current_angular_speed > self.target_angular_speed:
                self.current_angular_speed = max(self.target_angular_speed, self.current_angular_speed - self.deceleration)

            # Twist 메시지 생성 및 발행
            twist_msg = {
                'linear': {'x': self.current_linear_speed, 'y': 0.0, 'z': 0.0},
                'angular': {'x': 0.0, 'y': 0.0, 'z': self.current_angular_speed}
            }
            self.publisher.publish(roslibpy.Message(twist_msg))

            # 설정된 주기에 맞춰 대기
            time.sleep(1.0 / self.update_rate)
        logging.info("로봇 제어 루프 종료.")

    def start(self):
        """제어 루프 스레드를 시작합니다."""
        if not self._update_thread.is_alive():
            self._update_thread.start()

    def stop(self):
        """제어 루프 스레드를 안전하게 종료합니다."""
        self._shutdown_event.set()
        self._update_thread.join()