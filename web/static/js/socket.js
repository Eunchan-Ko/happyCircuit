// DOM이 완전히 로드된 후에 스크립트가 실행되도록 하는 것이 안전합니다.
document.addEventListener('DOMContentLoaded', (event) => {
    // 0. 전역변수 설정
    let isRobotConnected = false;
    const socket = io.connect(location.protocol + '//' + document.domain + ':' + location.port);
    const statusDiv = document.getElementById('status');
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
        console.log('상태 업데이트 수신:', data); // 디버깅용 로그

        // 로봇 연결 상태 업데이트
        const isNowConnected = data.pi_slam && data.pi_slam.rosbridge_connected;
        if (isRobotConnected !== isNowConnected) {
            isRobotConnected = isNowConnected;
            updateConnectionStatusUI();
        }

        // CV(카메라) 연결 상태 및 비디오 스트림 업데이트
        const isCvConnected = data.pi_cv && data.pi_cv.connected;
        updateVideoUI(isCvConnected, data.image);
    });

    // 3. 서버와 연결이 끊겼을 때
    socket.on('disconnect', () => {
        console.error('Socket.IO 서버와의 연결이 끊겼습니다.');
        isRobotConnected = false;
        updateConnectionStatusUI();
        updateVideoUI(false); // 비디오도 연결 끊김으로 처리
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

    // 연결 상태 UI 업데이트
    function updateConnectionStatusUI() {
        if (isRobotConnected) {
            statusDiv.textContent = '연결됨';
            statusDiv.style.backgroundColor = '#28a745'; // 초록색
        } else {
            statusDiv.textContent = '연결 안됨';
            statusDiv.style.backgroundColor = '#dc3545'; // 빨간색
        }
    }

    // 비디오 관련 UI 업데이트 함수 (조건 강화)
    function updateVideoUI(isCvConnected, imageBase64) {
        // isCvConnected가 true이고, imageBase64 데이터가 유효한 문자열일 경우에만 비디오 표시
        if (isCvConnected && imageBase64 && imageBase64.length > 100) {
            videoStream.style.display = 'block';
            videoOverlay.style.display = 'block';
            videoStream.src = 'data:image/jpeg;base64,' + imageBase64;
        } else {
            videoStream.style.display = 'none';
            videoOverlay.style.display = 'flex';
            videoStream.src = ''; // 소스를 비워 깨진 이미지 아이콘 방지
        }
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
    updateVideoUI(false);
});

