document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('mapCanvas');
    const ctx = canvas.getContext('2d');

    // 지도 및 로봇 위치 데이터를 저장할 상태 변수
    let currentMap = null;
    let robotPose = null; // 로봇의 현재 위치 및 방향

    if (typeof socket === 'undefined') {
        console.error('Socket.IO is not available. Make sure socket.js is loaded before map_renderer.js');
        return;
    }

    /**
     * 지도, 원점, 로봇 위치를 포함한 전체 캔버스를 다시 그리는 메인 함수
     */
    function redrawCanvas() {
        if (!currentMap) {
            return;
        }
        // 1. 지도 그리기
        drawMap(currentMap);

        // 2. 지도 원점 그리기
        drawOrigin(currentMap);

        // 3. 로봇 위치 그리기
        if (robotPose) {
            drawRobot(currentMap, robotPose);
        }
    }

    /**
     * 서버로부터 받은 지도 데이터를 Canvas에 그리는 함수
     */
    function drawMap(map) {
        const { width, height, data } = map;
        
        if (canvas.width !== width) canvas.width = width;
        if (canvas.height !== height) canvas.height = height;
        
        const imageData = ctx.createImageData(width, height);

        for (let i = 0; i < data.length; i++) {
            const x = i % width;
            const y = height - 1 - Math.floor(i / width);
            const pixelIndex = (y * width + x) * 4;

            let R, G, B;
            const value = data[i];
            if (value === -1) { [R, G, B] = [128, 128, 128]; } // 알 수 없는 영역 (회색)
            else if (value === 0) { [R, G, B] = [255, 255, 255]; } // 비어있는 영역 (흰색)
            else { [R, G, B] = [0, 0, 0]; } // 점유된 영역 (검은색)

            imageData.data[pixelIndex] = R;
            imageData.data[pixelIndex + 1] = G;
            imageData.data[pixelIndex + 2] = B;
            imageData.data[pixelIndex + 3] = 255;
        }
        ctx.putImageData(imageData, 0, 0);
    }

    /**
     * 지도 위에 원점(origin)을 그리는 함수
     */
    function drawOrigin(map) {
        const { resolution, origin, height } = map;
        const pixelX = (0 - origin.x) / resolution;
        const pixelY = height - ((0 - origin.y) / resolution);

        // 파란색 십자선으로 원점 표시
        ctx.strokeStyle = 'blue';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(pixelX - 10, pixelY);
        ctx.lineTo(pixelX + 10, pixelY);
        ctx.moveTo(pixelX, pixelY - 10);
        ctx.lineTo(pixelX, pixelY + 10);
        ctx.stroke();
    }

    /**
     * 지도 위에 로봇의 현재 위치를 그리는 함수
     * @param {object} map - 지도 데이터
     * @param {object} pose - 로봇의 위치 및 방향 데이터 ({ translation: { x, y, z }, rotation: { x, y, z, w } })
     */
    function drawRobot(map, pose) {
        const { resolution, origin, height } = map;
        const { translation } = pose;

        // 로봇의 월드 좌표를 캔버스 픽셀 좌표로 변환
        const pixelX = (translation.x - origin.x) / resolution;
        const pixelY = height - ((translation.y - origin.y) / resolution);

        // 빨간색 점으로 로봇 위치 표시
        ctx.fillStyle = 'red';
        ctx.beginPath();
        ctx.arc(pixelX, pixelY, 3, 0, 2 * Math.PI); // 반지름 5px
        ctx.fill();
    }


    // --- Socket.IO 이벤트 리스너 ---

    // 'map_update' 이벤트를 수신하면 지도 데이터를 저장하고 캔버스를 다시 그립니다.
    socket.on('map_update', (mapData) => {
        currentMap = mapData;
        redrawCanvas();
    });

    // 'tf_update' 이벤트를 수신하면 로봇 위치 데이터를 저장하고 캔버스를 다시 그립니다.
    socket.on('tf_update', (poseData) => {
        console.log("Received tf_update event:", poseData); // 1. 수신된 전체 데이터 확인

        // odom 프레임 기준으로 base_footprint의 transform을 찾습니다.
        const baseLinkTransform = poseData.transforms.find(t => t.header.frame_id === 'odom' && t.child_frame_id === 'base_footprint');
        
        if (baseLinkTransform) {
            console.log("Found base_link transform:", baseLinkTransform.transform); // 2. 찾은 transform 확인
            robotPose = baseLinkTransform.transform;
            redrawCanvas();
        } else {
            // odom -> base_link를 찾지 못한 경우, 다른 일반적인 transform(map -> odom)을 로깅하여 데이터를 확인합니다.
            const odomTransform = poseData.transforms.find(t => t.header.frame_id === 'map' && t.child_frame_id === 'odom');
            if (odomTransform) {
                console.log("Could not find odom -> base_link, but found map -> odom:", odomTransform);
            }
        }
    });

    console.log('Map renderer initialized and waiting for map and tf data...');
});
