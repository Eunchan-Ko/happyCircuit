import time
import threading
import roslibpy
import logging

class SmoothRobotController:
    """
    로봇의 주행을 부드럽게 가속/감속하며 제어하는 클래스.
    백그라운드 스레드에서 주기적으로 속도를 업데이트하며, activate/deactivate를 통해 발행 여부를 제어할 수 있습니다.
    """
    def __init__(self, publisher):
        if not publisher:
            raise ValueError("Publisher는 필수입니다.")
        self.publisher = publisher

        # --- 제어 파라미터 ---
        self.max_linear_speed = 0.08 # linear 방향 최고속도
        self.max_angular_speed = 1.0 # angular 방향 최고속도
        self.acceleration = 0.02 # linear 방향 가속도
        self.deceleration = 0.02 # linear 방향 감속도
        self.angle_acceleration = 0.5 # angular 방향 가속도
        self.angle_deceleration = 0.5 # angular 방향 감속도
        self.update_rate = 20 # Hz

        # --- 상태 변수 ---
        self.target_linear_speed = 0.0
        self.target_angular_speed = 0.0
        self.current_linear_speed = 0.0
        self.current_angular_speed = 0.0

        # --- 스레드 제어 이벤트 ---
        self._is_active = threading.Event()    # 발행 활성화/비활성화를 제어
        self._shutdown_event = threading.Event() # 스레드를 완전히 종료할 때 사용
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._update_thread.start() # 스레드를 즉시 시작

    def set_direction(self, direction):
        """프론트엔드로부터 방향 명령을 받아 목표 속도를 설정합니다."""
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
        """백그라운드에서 실행되며, 활성화 상태일 때만 속도를 계산하고 토픽을 발행합니다."""
        logging.info("로봇 제어 루프 시작.")
        while not self._shutdown_event.is_set():
            # _is_active 이벤트가 설정될 때까지 여기서 대기(블로킹)합니다.
            # CPU를 낭비하지 않고 효율적으로 대기할 수 있습니다.
            self._is_active.wait()

            # 루프가 활성화된 동안에만 아래 로직을 실행합니다.
            while self._is_active.is_set() and not self._shutdown_event.is_set():
                # 선형 속도 업데이트
                if self.current_linear_speed < self.target_linear_speed:
                    self.current_linear_speed = min(self.target_linear_speed, self.current_linear_speed + self.acceleration)
                elif self.current_linear_speed > self.target_linear_speed:
                    self.current_linear_speed = max(self.target_linear_speed, self.current_linear_speed - self.deceleration)

                # 각속도 업데이트
                if self.current_angular_speed < self.target_angular_speed:
                    self.current_angular_speed = min(self.target_angular_speed, self.current_angular_speed + self.angle_acceleration)
                elif self.current_angular_speed > self.target_angular_speed:
                    self.current_angular_speed = max(self.target_angular_speed, self.current_angular_speed - self.angle_deceleration)

                # Twist 메시지 생성 및 발행
                twist_msg = {
                    'linear': {'x': self.current_linear_speed, 'y': 0.0, 'z': 0.0},
                    'angular': {'x': 0.0, 'y': 0.0, 'z': self.current_angular_speed}
                }
                self.publisher.publish(roslibpy.Message(twist_msg))

                time.sleep(1.0 / self.update_rate)
        
        logging.info("로봇 제어 루프 완전 종료.")

    def activate(self):
        """제어 루프의 발행을 활성화합니다."""
        logging.info("[Controller] 활성화됨.")
        self._is_active.set()

    def deactivate(self):
        """제어 루프의 발행을 비활성화하고 로봇을 정지시킵니다."""
        logging.info("[Controller] 비활성화됨.")
        self._is_active.clear()
        # 비활성화 시 즉시 정지하도록 목표 속도를 0으로 설정
        self.target_linear_speed = 0.0
        self.target_angular_speed = 0.0
        # 현재 속도도 0으로 강제하여 즉시 발행을 멈춤
        self.current_linear_speed = 0.0
        self.current_angular_speed = 0.0


    def shutdown(self):
        """제어 루프 스레드를 안전하게 완전히 종료합니다."""
        logging.info("[Controller] 완전 종료 신호 수신.")
        self._shutdown_event.set()
        # wait() 상태에서 스레드가 멈춰있을 수 있으므로, set()을 호출하여 깨워줍니다.
        self._is_active.set() 
        if self._update_thread.is_alive():
            self._update_thread.join()
