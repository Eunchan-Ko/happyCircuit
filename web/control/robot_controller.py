import roslibpy
import logging

# 이 파일은 오직 '로봇을 조작하는 방법'에 대한 코드만 담습니다.

def send_drive_command(cmd_vel_publisher, direction):
    """
    퍼블리셔와 방향을 인자로 받아서, 실제 Twist 메시지를 발행하는 함수.
    이 함수는 더 이상 self에 의존하지 않습니다.
    """
    if not cmd_vel_publisher:
        logging.warning("[Control] cmd_vel 퍼블리셔가 준비되지 않았습니다.")
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

    logging.info(f"[Control] 로봇 제어 명령 발행: {direction}")
    cmd_vel_publisher.publish(roslibpy.Message(twist_msg))