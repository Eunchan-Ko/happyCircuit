// DOM이 완전히 로드된 후에 스크립트가 실행되도록 하는 것이 안전합니다.
document.addEventListener('DOMContentLoaded', (event) => {
    // 0. 전역변수 설정
    let isRobotConnected = false;
    const socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);
    const robotStatusDiv = document.getElementById('robot-status');
    const imageStatusDiv = document.getElementById('image-status');
    const allControlButtons = document.querySelectorAll('.d-pad .button');
    const videoStream = document.getElementById('video-stream');
    const videoOverlay = document.getElementById('video-overlay');

    /**
     * =======================================
     *           이벤트 리스너 등록
     * =======================================
     */

    // 1. 서버와 성공적으로 연결되었을 때
    socket.on('connect', () => {
        console.log('Socket.IO 서버에 성공적으로 연결되었습니다. ID:', socket.id);
    });

    // 2. 서버로부터 상태 업데이트를 수신했을 때
    socket.on('status_update', (data) => {
        console.log('상태 업데이트 수신:', data);
        // 페이지 경로에 따라 적절한 UI 업데이트 함수 호출
        if (document.querySelector('.home-container')) {
            updateIndexPageUI(data);
        }
        if (document.querySelector('.control-container')) {
            updateControlPageUI(data);
        }
    });

    // 3. 서버와 연결이 끊겼을 때
    socket.on('disconnect', () => {
        console.error('Socket.IO 서버와의 연결이 끊겼습니다.');
        const defaultStatus = createDefaultStatus();
        if (document.querySelector('.home-container')) {
            updateIndexPageUI(defaultStatus);
        }
        if (document.querySelector('.control-container')) {
            updateControlPageUI(defaultStatus);
        }
    });

    /**
     * =======================================
     *           로봇 제어 함수
     * =======================================
     */

    // 제어 명령을 서버로 전송하는 함수
    function sendCommand(direction) {
        if (!isRobotConnected) {
            console.warn('로봇과 연결되지 않았습니다. 명령을 전송할 수 없습니다.');
            alert('로봇과 연결되지 않았습니다.\n서버 및 로봇의 상태를 확인해주세요.');
            return;
        }
        console.log(`명령 전송: ${direction}`);
        socket.emit('drive_command', { 'direction': direction });
        updateButtonUI(direction);
    }

    /**
     * =======================================
     *           UI 업데이트 함수
     * =======================================
     */

    // index.html의 UI를 업데이트하는 함수
    function updateIndexPageUI(data) {
        // 전역 isRobotConnected 변수 업데이트
        isRobotConnected = data.pi_slam && data.pi_slam.rosbridge_connected;

        // DOM 요소 가져오기
        const slamConnectedEl = document.getElementById('slam-connected');
        const slamStatusEl = document.getElementById('slam-status');
        const batteryProgressEl = document.getElementById('battery-progress');
        const batteryPercentageEl = document.getElementById('battery-percentage');
        const batteryVoltageEl = document.getElementById('battery-voltage');
        const odomXEl = document.getElementById('odom-x');
        const odomYEl = document.getElementById('odom-y');
        const odomThetaEl = document.getElementById('odom-theta');
        const piCvConnectedEl = document.getElementById('pi-cv-connected');
        const piCvStatusEl = document.getElementById('pi-cv-status');

        // 1. ROS 연결 상태
        if (slamConnectedEl) {
            if (isRobotConnected) {
                slamConnectedEl.textContent = '연결됨';
                slamConnectedEl.className = 'status-connected';
                slamStatusEl.textContent = 'ROS-Bridge에 성공적으로 연결되었습니다.';
            } else {
                slamConnectedEl.textContent = '연결 안됨';
                slamConnectedEl.className = 'status-disconnected';
                slamStatusEl.textContent = '서버로부터 정보 수신 대기 중...';
            }
        }

        // 2. 배터리 상태
        const battery = data.pi_slam && data.pi_slam.battery;
        if (batteryPercentageEl) {
            if (isRobotConnected && battery && battery.percentage !== 'N/A') {
                const percentage = parseFloat(battery.percentage);
                batteryPercentageEl.textContent = `${percentage.toFixed(1)}%`;
                batteryVoltageEl.textContent = parseFloat(battery.voltage).toFixed(2);
                batteryProgressEl.style.width = `${percentage}%`;
                if (percentage < 20) batteryProgressEl.style.backgroundColor = '#dc3545';
                else if (percentage < 50) batteryProgressEl.style.backgroundColor = '#ffc107';
                else batteryProgressEl.style.backgroundColor = '#28a745';
            } else {
                batteryPercentageEl.textContent = 'N/A';
                batteryVoltageEl.textContent = 'N/A';
                batteryProgressEl.style.width = '0%';
            }
        }

        // 3. Odometry 정보
        const odom = data.pi_slam && data.pi_slam.last_odom;
        if (odomXEl) {
            if (isRobotConnected && odom && odom.x !== 'N/A') {
                odomXEl.textContent = odom.x;
                odomYEl.textContent = odom.y;
                odomThetaEl.textContent = odom.theta;
            } else {
                odomXEl.textContent = 'N/A';
                odomYEl.textContent = 'N/A';
                odomThetaEl.textContent = 'N/A';
            }
        }

        // 4. 이미지 모듈(CV) 연결 상태
        const isCvConnected = data.pi_cv && data.pi_cv.connected;
        if (piCvConnectedEl) {
            if (isCvConnected) {
                piCvConnectedEl.textContent = '연결됨';
                piCvConnectedEl.className = 'status-connected';
                piCvStatusEl.textContent = '이미지 스트림 서버에 연결되었습니다.';
            } else {
                piCvConnectedEl.textContent = '연결 안됨';
                piCvConnectedEl.className = 'status-disconnected';
                piCvStatusEl.textContent = '서버로부터 정보 수신 대기 중...';
            }
        }
    }

    // control.html의 UI를 업데이트하는 함수
    function updateControlPageUI(data) {
        // 전역 isRobotConnected 변수 업데이트
        isRobotConnected = data.pi_slam && data.pi_slam.rosbridge_connected;
        const isCvConnected = data.pi_cv && data.pi_cv.connected;
        console.log('Updating control page UI. Robot connected:', isRobotConnected, 'CV connected:', isCvConnected);

        // control.html의 연결 상태 표시
        if (robotStatusDiv) {
            if (isRobotConnected) {
                robotStatusDiv.textContent = 'ROBOT: 연결됨';
                robotStatusDiv.style.color = '#28a745';
            } else {
                robotStatusDiv.textContent = 'ROBOT: 연결 안됨';
                robotStatusDiv.style.color = '#dc3545';
            }
        }

        if (imageStatusDiv) {
            if (isCvConnected) {
                imageStatusDiv.textContent = 'IMAGE: 연결됨';
                imageStatusDiv.style.color = '#28a745';
            } else {
                imageStatusDiv.textContent = 'IMAGE: 연결 안됨';
                imageStatusDiv.style.color = '#dc3545';
            }
        }

        // 비디오 UI 업데이트
        if (videoStream) {
            // control.html 에서는 data.image가 아닌 new_image 이벤트를 통해 이미지를 받습니다.
            // 이 부분은 new_image 이벤트 핸들러에서 처리해야 합니다.
            // 여기서는 연결 상태에 따른 오버레이만 제어합니다.
            if (isCvConnected) {
                 videoOverlay.style.display = 'none';
            } else {
                videoStream.style.display = 'none';
                videoOverlay.style.display = 'flex';
                videoStream.src = '';
            }
        }
    }
    
    // new_image 이벤트를 받았을 때 video-stream 업데이트
    socket.on('new_image', (data) => {
        if (videoStream && data.image && data.image.length > 100) {
            videoStream.style.display = 'block';
            videoOverlay.style.display = 'none';
            videoStream.src = 'data:image/jpeg;base64,' + data.image;
        }
    });

    // 연결 끊김 시 사용할 기본 상태 객체 생성 함수
    function createDefaultStatus() {
        return {
            pi_cv: { connected: false, image: null },
            pi_slam: {
                rosbridge_connected: false,
                last_odom: { x: "N/A", y: "N/A", theta: "N/A" },
                battery: { percentage: "N/A", voltage: "N/A" }
            }
        };
    }

    // 버튼 UI 업데이트
    function updateButtonUI(direction) {
        allControlButtons.forEach(btn => btn.classList.remove('active-command'));
        const targetButton = document.getElementById(direction);
        if (targetButton) {
            targetButton.classList.add('active-command');
            // 'stop' 명령이 아닐 경우, 잠시 후 자동으로 active 클래스를 제거하지 않음 (누르고 있을 때 계속 활성화)
        } else if (direction === 'stop') {
            // 'stop'은 특정 방향 버튼이 아니므로 별도 처리
            const stopButton = document.getElementById('stop');
            if (stopButton) {
                stopButton.classList.add('active-command');
                setTimeout(() => {
                    stopButton.classList.remove('active-command');
                }, 200);
            }
        }
    }

    /**
     * =======================================
     *        사용자 입력 이벤트 리스너
     * =======================================
     */

    // 1. 마우스 및 터치 이벤트
    const buttons = [
        { id: 'forward',  direction: 'forward' },
        { id: 'backward', direction: 'backward' },
        { id: 'left',     direction: 'left' },
        { id: 'right',    direction: 'right' }
    ];

    buttons.forEach(btnInfo => {
        const element = document.getElementById(btnInfo.id);
        if (!element) return;

        // 데스크탑용 마우스 이벤트
        element.addEventListener('mousedown', () => sendCommand(btnInfo.direction));
        element.addEventListener('mouseup', () => sendCommand('stop'));
        element.addEventListener('mouseleave', () => sendCommand('stop'));

        // 모바일용 터치 이벤트
        element.addEventListener('touchstart', (e) => { e.preventDefault(); sendCommand(btnInfo.direction); });
        element.addEventListener('touchend', () => sendCommand('stop'));
    });

    const stopButton = document.getElementById('stop');
    if(stopButton) {
        stopButton.addEventListener('click', () => sendCommand('stop'));
    }


    // 2. 키보드 이벤트
    let keydownState = {};
    document.addEventListener('keydown', (event) => {
        if (keydownState[event.key]) return;
        keydownState[event.key] = true;

        let command = null;
        switch (event.key) {
            case 'w': case 'W': case 'ㅈ': case 'ArrowUp':    command = 'forward'; break;
            case 's': case 'S': case 'ㄴ': case 'ArrowDown':  command = 'backward'; break;
            case 'a': case 'A': case 'ㅁ': case 'ArrowLeft':  command = 'left'; break;
            case 'd': case 'D': case 'ㅇ': case 'ArrowRight': command = 'right'; break;
            case ' ': /* Spacebar */                           command = 'stop'; break;
        }
        if(command) sendCommand(command);
    });

    document.addEventListener('keyup', (event) => {
        keydownState[event.key] = false;
        const stopKeys = [' ']; // 스페이스바는 뗄 때 stop을 보내지 않음 (이미 눌렀을 때 보냈으므로)
        const controlKeys = ['w', 'W', 'ㅈ', 'ArrowUp', 's', 'S', 'ㄴ', 'ArrowDown', 'a', 'A', 'ㅁ', 'ArrowLeft', 'd', 'D', 'ㅇ', 'ArrowRight'];

        if (controlKeys.includes(event.key) && !stopKeys.includes(event.key)) {
            sendCommand('stop');
            // 키를 떼면 모든 버튼의 활성 상태를 제거
            allControlButtons.forEach(btn => btn.classList.remove('active-command'));
        }
    });

    // 페이지 로드 시 초기 UI 상태 설정
    //updateVideoUI(false);
});

