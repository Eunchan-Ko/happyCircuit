document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('mapCanvas');
    const ctx = canvas.getContext('2d');

    // 지도 데이터를 저장할 상태 변수
    let currentMap = null;

    if (typeof socket === 'undefined') {
        console.error('Socket.IO is not available. Make sure socket.js is loaded before map_renderer.js');
        return;
    }

    /**
     * 지도와 원점을 포함한 전체 캔버스를 다시 그리는 메인 함수
     */
    function redrawCanvas() {
        if (!currentMap) {
            return;
        }
        // 1. 지도 그리기
        drawMap(currentMap);

        // 2. 지도 원점 그리기
        drawOrigin(currentMap);
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

    // --- Socket.IO 이벤트 리스너 ---

    // 'map_update' 이벤트를 수신하면 지도 데이터를 저장하고 캔버스를 다시 그립니다.
    socket.on('map_update', (mapData) => {
        currentMap = mapData;
        redrawCanvas();
    });

    console.log('Map renderer initialized and waiting for map data...');
});
