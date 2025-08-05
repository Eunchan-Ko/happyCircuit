// 웹서버의 Socket.IO에 연결
// DOM이 완전히 로드된 후에 스크립트가 실행되도록 하는 것이 안전합니다.
document.addEventListener('DOMContentLoaded', (event) => {

    const socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);

    /**
     * event listener 등록
     */
    // 서버와 성공적으로 연결되었을 때 콘솔에 로그를 남긴다.
    socket.on('connect', () => {
        console.log('Socket.IO 서버에 성공적으로 연결되었습니다.');
        console.log('서버에 연결되었습니다. ID:', socket.id);
    });

    // 'status_update' 이벤트를 수신 대기
    socket.on('status_update', (data) => {
        console.log('상태 업데이트 수신:', data);

        // CV 모듈 정보 업데이트
        const slamConnectedEl = document.getElementById('slam-connected');
        const slamStatusEl = document.getElementById('slam-status');
        const odomXEl = document.getElementById('odom-x');
        const odomYEl = document.getElementById('odom-y');
        const odomThetaEl = document.getElementById('odom-theta'); // 방향(theta)을 위한 요소

        // 배터리 관련 요소 (HTML에 추가 필요)
        const batteryPercentageEl = document.getElementById('battery-percentage');
        const batteryVoltageEl = document.getElementById('battery-voltage');
        const batteryProgressEl = document.getElementById('battery-progress');

        // --- pi_slam 객체가 있는지 확인 ---
        const slamData = data.pi_slam;
        if (!slamData) {
            console.error("수신된 데이터에 'pi_slam' 객체가 없습니다.");
            return;
        }
        // ✅ [수정] SLAM 모듈 연결 상태 업데이트
        if (slamData.rosbridge_connected) {
            slamConnectedEl.textContent = '연결됨';
            slamConnectedEl.style.color = 'green';
            slamStatusEl.textContent = '실시간 데이터 수신 중...';
        } else {
            slamConnectedEl.textContent = '연결 안됨';
            slamConnectedEl.style.color = 'red';
            slamStatusEl.textContent = '서버로부터 정보 수신 대기 중...';
        }

        // ✅ [수정] Odometry 데이터 업데이트
        if (slamData.last_odom) {
            odomXEl.textContent = slamData.last_odom.x;
            odomYEl.textContent = slamData.last_odom.y;
            odomThetaEl.textContent = slamData.last_odom.theta;
        }

        // ✅ [수정] 배터리 데이터 업데이트
        if (slamData.battery && batteryProgressEl && batteryPercentageEl && batteryVoltageEl) {
            const percentage = slamData.battery.percentage;
            const voltage = slamData.battery.voltage;

            if (percentage !== 'N/A') {
                batteryProgressEl.style.width = percentage + '%';
                batteryPercentageEl.textContent = percentage + '%';
            } else {
                batteryProgressEl.style.width = '0%';
                batteryPercentageEl.textContent = 'N/A';
            }
            batteryVoltageEl.textContent = voltage;
        }
    });

    socket.on('disconnect', () => {
        console.error('Socket.IO 서버와의 연결이 끊겼습니다.');
        console.log('서버와의 연결이 끊겼습니다.');
    });
});