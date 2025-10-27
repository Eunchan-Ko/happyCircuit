import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
import numpy as np
import math
import os
import subprocess

# TF2\uc640 \uad00\ub828\ub41c \ub77c\uc774\ube0c\ub7ec\ub9ac\ub97c \ucd94\uac00\ud569\ub2c8\ub2e4.
import tf2_ros
from tf2_ros import LookupException, ConnectivityException, ExtrapolationException
from tf_transformations import euler_from_quaternion
from std_msgs.msg import String # 추가

class ExplorerNode(Node):
    def __init__(self):
        super().__init__('explorer')
        self.get_logger().info("Explorer Node Started")

        # --- 상태 관리 변수 ---
        # 'EXPLORING': 탐색 중
        # 'RETURNING_HOME': 시작 지점으로 복귀 중
        # 'SHUTTING_DOWN': 종료 중
        self.state = 'EXPLORING'
        self.get_logger().info(f"Initial Setting. state : EXPLORING")
        self.start_position = None # 탐색 시작 위치를 저장할 변수
        self.frontier_failure_count = 0

        # Subscriber to the map topic
        self.map_sub = self.create_subscription(
            OccupancyGrid, '/map', self.map_callback, 10)

        # Action client for navigation
        self.nav_to_pose_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')

        # Publisher for exploration status
        self.status_publisher = self.create_publisher(String, '/exploration_status', 10)

        # Visited frontiers set
        self.visited_frontiers = set()

        # Map and pose data
        self.map_data = None
        self.robot_pose = None # \ub85c\ubd07\uc758 \uc704\uce58\uc640 \ubc29\ud5a5\uc744 \ubaa8\ub450 \uc800\uc7a5\ud560 \ubcc0\uc218

        # --- TF2 \ub9ac\uc2a4\ub108 \ucd08\uae30\ud654 ---
        self.tf_buffer = tf2_ros.Buffer()
        self.tf_listener = tf2_ros.TransformListener(self.tf_buffer, self)

        # --- \ub85c\ubd07 \uc790\uc138\ub97c \uc8fc\uae30\uc801\uc73c\ub85c \uc5c5\ub370\uc774\ud2b8\ud558\uae30 \uc704\ud55c \ud0c0\uc774\uba38 ---
        self.pose_update_timer = self.create_timer(1.0, self.update_robot_pose)

        # Timer for periodic exploration
        self.timer = self.create_timer(5.0, self.explore)

    def map_callback(self, msg):
        self.map_data = msg

    # --- \ucd94\uac00\ub41c \uba54\uc11c\ub4dc: TF2\ub97c \uc0ac\uc6a9\ud558\uc5ec \ub85c\ubd07 \uc790\uc138 \uc5c5\ub370\uc774\ud2b8 ---
    def update_robot_pose(self):
        """Periodically update the robot's pose using TF2."""
        # \uc885\ub8cc \uc911\uc5d0\ub294 \uc790\uc138 \uc5c5\ub370\uc774\ud2b8\ub97c \uc911\ub2e8\ud569\ub2c8\ub2e4.
        if self.state == 'SHUTTING_DOWN':
            return
        try:
            # 'map' \ud504\ub808\uc784 \uae30\uc900\uc73c\ub85c 'base_link'\uc758 transform\uc744 \uc870\ud68c\ud569\ub2c8\ub2e4.
            trans = self.tf_buffer.lookup_transform('map', 'base_link', rclpy.time.Time())
            self.robot_pose = trans.transform

            # \ud0d0\uc0c9 \uc2dc\uc791 \uc704\uce58\ub97c \ud55c \ubc88\ub9cc \uae30\ub85d\ud569\ub2c8\ub2e4.
            if self.start_position is None and self.robot_pose is not None:
                self.start_position = (self.robot_pose.translation.x, self.robot_pose.translation.y)
                self.get_logger().info(f"Start position captured: ({self.start_position[0]:.2f}, {self.start_position[1]:.2f})")

        except (LookupException, ConnectivityException, ExtrapolationException) as e:
            self.get_logger().warn(f"Could not get robot pose: {e}")

    def navigate_to(self, x, y):
        goal_msg = PoseStamped()
        goal_msg.header.frame_id = 'map'
        goal_msg.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.position.x = x
        goal_msg.pose.position.y = y
        goal_msg.pose.orientation.w = 1.0  # Facing forward

        nav_goal = NavigateToPose.Goal()
        nav_goal.pose = goal_msg

        self.get_logger().info(f"Navigating to goal: x={x:.2f}, y={y:.2f}")

        self.nav_to_pose_client.wait_for_server()
        send_goal_future = self.nav_to_pose_client.send_goal_async(nav_goal)
        send_goal_future.add_done_callback(self.goal_response_callback)

    def goal_response_callback(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warning("Goal rejected!")
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self.navigation_complete_callback)

    def navigation_complete_callback(self, future):
        try:
            result = future.result().result
            # self.get_logger().info(f"Navigation completed with result: {result}")

            # --- \ub85c\uc9c1 \ucd94\uac00: \ubcf5\uadc0 \uc0c1\ud0dc\uc5d0\uc11c \ub124\ube44\uac8c\uc774\uc158\uc774 \uc644\ub8cc\ub418\uba74 \ub9f5 \uc800\uc7a5 ---
            if self.state == 'RETURNING_HOME':
                self.get_logger().info("Successfully returned to start position. Saving map.")
                self.save_map_and_shutdown()

        except Exception as e:
            self.get_logger().error(f"Navigation failed: {e}")
            # --- \ub85c\uc9c1 \ucd94\uac00: \ubcf5\uadc0 \uc911 \ub124\ube44\uac8c\uc774\uc158 \uc2e4\ud328 \uc2dc\uc5d0\ub3c4 \ub9f5 \uc800\uc7a5 ---
            if self.state == 'RETURNING_HOME':
                self.get_logger().error("Failed to return to start. Saving map at current location and shutting down.")
                self.save_map_and_shutdown()

    def find_frontiers(self, map_array):
        """
        Detect frontiers in the occupancy grid map.
        A frontier is a free cell that has an unknown neighbor.
        """
        frontiers = []
        rows, cols = map_array.shape

        for r in range(1, rows - 1):
            for c in range(1, cols - 1):
                # '0'\uc740 \ube44\uc5b4\uc788\ub294 \uacf5\uac04(free space)\uc744 \uc758\ubbf8\ud569\ub2c8\ub2e4.
                if map_array[r, c] == 0:
                    # 8\ubc29\ud5a5\uc758 \uc774\uc6c3 \uc140\ub4e4\uc744 \ud655\uc778\ud569\ub2c8\ub2e4.
                    neighbors = map_array[r-1:r+2, c-1:c+2]
                    # \uc774\uc6c3 \uc911\uc5d0 '-1'(unknown)\uc774 \ud558\ub098\ub77c\ub3c4 \uc788\ub2e4\uba74 \ud504\ub860\ud2f0\uc5b4\ub85c \uac04\uc8fc\ud569\ub2c8\ub2e4.
                    if np.any(neighbors == -1):
                        frontiers.append((r, c))

        return frontiers

    def choose_frontier(self, frontiers):
        """
        Choose the closest frontier that is in front of the robot.
        """
        if self.robot_pose is None:
            self.get_logger().warning("Robot pose is not available yet. Cannot choose a frontier.")
            return None

        # \ub85c\ubd07\uc758 \ud604\uc7ac \uc704\uce58 (map \uc88c\ud45c\uacc4)
        robot_x = self.robot_pose.translation.x
        robot_y = self.robot_pose.translation.y

        # \ub85c\ubd07\uc758 \ud604\uc7ac \ubc29\ud5a5 (yaw)\uc744 \ucffc\ud130\ub2c8\uc5b8\uc73c\ub85c\ubd80\ud130 \uacc4\uc0b0\ud569\ub2c8\ub2e4.
        orientation_q = self.robot_pose.rotation
        _, _, robot_yaw = euler_from_quaternion([
            orientation_q.x, orientation_q.y, orientation_q.z, orientation_q.w])

        min_distance = float('inf')
        chosen_frontier = None

        for frontier in frontiers:
            if frontier in self.visited_frontiers:
                continue

            # \ud504\ub860\ud2f0\uc5b4\uc758 \uc6d4\ub4dc \uc88c\ud45c\ub97c \uacc4\uc0b0\ud569\ub2c8\ub2e4.
            frontier_x = frontier[1] * self.map_data.info.resolution + self.map_data.info.origin.position.x
            frontier_y = frontier[0] * self.map_data.info.resolution + self.map_data.info.origin.position.y

            # \ub85c\ubd07 \uc704\uce58\uc5d0\uc11c \ud504\ub860\ud2f0\uc5b4\ub85c \ud5a5\ud558\ub294 \uac01\ub3c4\ub97c \uacc4\uc0b0\ud569\ub2c8\ub2e4.
            angle_to_frontier = math.atan2(frontier_y - robot_y, frontier_x - robot_x)

            # \ub85c\ubd07\uc758 \ud604\uc7ac \ubc29\ud5a5\uacfc \ud504\ub860\ud2f0\uc5b4\ub85c\uc758 \ubc29\ud5a5 \ucc28\uc774\ub97c \uacc4\uc0b0\ud569\ub2c8\ub2e4.
            angle_diff = abs(robot_yaw - angle_to_frontier)
            # \uac01\ub3c4 \ucc28\uc774\uac00 180\ub3c4(pi)\ub97c \ub118\uc9c0 \uc54a\ub3c4\ub85d \uc815\uaddc\ud654\ud569\ub2c8\ub2e4.
            if angle_diff > math.pi:
                angle_diff = 2 * math.pi - angle_diff

            # \ub85c\ubd07\uc758 \uc804\ubc29 \uc2dc\uc57c\uac01(\uc5ec\uae30\uc11c\ub294 +/- 90\ub3c4, \uc989 1.57 \ub77c\ub514\uc548) \ub0b4\uc5d0 \uc788\ub294\uc9c0 \ud655\uc778\ud569\ub2c8\ub2e4.
            if angle_diff > (11 * math.pi / 12.0):
                continue

            # \uc804\ubc29\uc5d0 \uc788\ub294 \ud504\ub860\ud2f0\uc5b4 \uc911\uc5d0\uc11c \uac00\uc7a5 \uac00\uae4c\uc6b4 \uac83\uc744 \uc120\ud0dd\ud569\ub2c8\ub2e4.
            distance = math.sqrt((robot_x - frontier_x)**2 + (robot_y - frontier_y)**2)
            if distance < min_distance:
                min_distance = distance
                chosen_frontier = frontier

        if chosen_frontier:
            self.visited_frontiers.add(chosen_frontier)
            self.get_logger().info(f"Chosen FORWARD frontier: {chosen_frontier} at distance {min_distance:.2f}m")
        else:
            self.get_logger().warning("No valid frontier found in front of the robot.")

        return chosen_frontier

    # --- \ucd94\uac00\ub41c \uba54\uc11c\ub4dc: \ub9f5 \uc800\uc7a5 \ubc0f \ub178\ub4dc \uc885\ub8cc ---
    def save_map_and_shutdown(self):
        # \uc774\ubbf8 \uc885\ub8cc \ud504\ub85c\uc138\uc2a4\uac00 \uc2dc\uc791\ub418\uc5c8\ub2e4\uba74 \uc911\ubcf5 \uc2e4\ud589 \ubc29\uc9c0
        if self.state == 'SHUTTING_DOWN':
            return

        self.get_logger().info("Starting shutdown process.")
        self.state = 'SHUTTING_DOWN'

        # \ub354 \uc774\uc0c1 \ud0d0\uc0c9/\uc790\uc138 \uc5c5\ub370\uc774\ud2b8 \ud0c0\uc774\uba38\uac00 \ub3cc\uc9c0 \uc54a\ub3c4\ub85d \ucde8\uc18c
        self.timer.cancel()
        self.pose_update_timer.cancel()

        # 탐사 종료 메시지 발행
        status_msg = String()
        status_msg.data = 'end'
        self.status_publisher.publish(status_msg)
        self.get_logger().info("Published 'end' to /exploration_status topic.")
        # 메시지가 확실히 발행되도록 잠시 대기
        self.create_timer(1.0, self._shutdown_node, oneshot=True)

    def _shutdown_node(self):
        map_file_path = os.path.join(os.path.expanduser('~'), 'my_explored_map')
        self.get_logger().info(f"Saving map to {map_file_path}...")

        try:
            # ros2 run nav2_map_server map_saver_cli -f <file_path> 명령어 실행
            subprocess.run(
                ['ros2', 'run', 'nav2_map_server', 'map_saver_cli', '-f', map_file_path],
                check=True, timeout=30
            )
            self.get_logger().info("Map saved successfully!")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            self.get_logger().error(f"Failed to save map: {e}")

        self.get_logger().info("Shutting down explorer node.")
        # 노드를 안전하게 종료하고 rclpy를 shutdown 시킵니다.
        self.destroy_node()
        rclpy.shutdown()

    def explore(self):
        # \ud0d0\uc0c9 \uc0c1\ud0dc\uac00 \uc544\ub2c8\uba74 explore \ud568\uc218\ub97c \uc2e4\ud589\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.
        if self.state != 'EXPLORING':
            self.get_logger().error(f"Check robot state. now : {self.state}, expect : EXPLORING")
            return

        if self.map_data is None:
            self.get_logger().warning("No map data available, cannot explore.")
            return

        if self.start_position is None:
            self.get_logger().info("Waiting for start position to be captured...")
            return

        map_array = np.array(self.map_data.data).reshape(
            (self.map_data.info.height, self.map_data.info.width))

        frontiers = self.find_frontiers(map_array)

        # --- \ub85c\uc9c1 \uc218\uc815: \ud504\ub860\ud2f0\uc5b4\uac00 \ub354 \uc774\uc0c1 \uc5c6\uc73c\uba74 \ubcf5\uadc0 \uc0c1\ud0dc\ub85c \uc804\ud658 ---
        if not frontiers:

            self.state = 'RETURNING_HOME'
            self.navigate_to(self.start_position[0], self.start_position[1])
            return

        chosen_frontier = self.choose_frontier(frontiers)

        if not chosen_frontier:
            self.frontier_failure_count += 1
            self.get_logger().warning(f"Failed to find a valid frontier to explorer. Failure count: {self.frontier_failure_count}")
        else:
            self.frontier_failure_count = 0

            goal_x = chosen_frontier[1] * self.map_data.info.resolution + self.map_data.info.origin.position.x
            goal_y = chosen_frontier[0] * self.map_data.info.resolution + self.map_data.info.origin.position.y
            self.navigate_to(goal_x, goal_y)
        # If failed twice, return to the recorded start position
        if self.frontier_failure_count == 40:
            self.get_logger().info("No more frontiers to explore. Exploration Complete!")
            self.get_logger().info("Failed to find a new frontier twice. Returning to start position.")
            self.state = 'RETURNING_HOME'
            self.navigate_to(self.start_position[0], self.start_position[1])
            return

def main(args=None):
    rclpy.init(args=args)
    explorer_node = ExplorerNode()
    try:
        rclpy.spin(explorer_node)
    except KeyboardInterrupt:
        explorer_node.get_logger().info("Exploration stopped by user")
    finally:
        # \ub178\ub4dc\uac00 \uc774\ubbf8 destroy_node()\uc640 rclpy.shutdown()\uc73c\ub85c \uc885\ub8cc\ub418\uc5c8\uc744 \uc218 \uc788\uc73c\ubbc0\ub85c
        # rclpy.ok()\ub97c \ud655\uc778\ud558\uc5ec \uc911\ubcf5 \ud638\ucd9c\uc744 \ubc29\uc9c0\ud569\ub2c8\ub2e4.
        if rclpy.ok():
            explorer_node.destroy_node()
            rclpy.shutdown()

if __name__ == '__main__':
    main()
