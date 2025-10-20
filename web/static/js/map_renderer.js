document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('mapCanvas');
    const ctx = canvas.getContext('2d');

    // base.html에 정의된 전역 socket 변수를 사용합니다.
    // 이 스크립트가 로드될 때 socket.io가 이미 연결되어 있다고 가정합니다.
    if (typeof socket === 'undefined') {
        console.error('Socket.IO is not available. Make sure socket.js is loaded before map_renderer.js');
        return;
    }

    /**
     * 서버로부터 받은 지도 데이터를 Canvas에 그리는 함수
     * @param {object} mapData - 'map_update' 이벤트로 받은 JSON 데이터
     */
    function drawMap(mapData) {
        const { width, height, data } = mapData;
        
        // 캔버스 크기를 지도 크기에 맞게 조정
        // 성능을 위해 크기가 다를 때만 업데이트
        if (canvas.width !== width) canvas.width = width;
        if (canvas.height !== height) canvas.height = height;
        
        const imageData = ctx.createImageData(width, height);

        for (let i = 0; i < data.length; i++) {
            // ROS 맵 데이터는 y축이 반전되어 있으므로 좌표 변환이 필요합니다.
            const x = i % width;
            const y = height - 1 - Math.floor(i / width);
            const pixelIndex = (y * width + x) * 4;

            let R, G, B;
            const value = data[i];
            if (value === -1) { // 알 수 없는 영역
                [R, G, B] = [128, 128, 128]; // 회색
            } else if (value === 0) { // 비어있는 영역
                [R, G, B] = [255, 255, 255]; // 흰색
            } else { // 점유된 영역 (1~100)
                [R, G, B] = [0, 0, 0];       // 검은색
            }

            imageData.data[pixelIndex] = R;
            imageData.data[pixelIndex + 1] = G;
            imageData.data[pixelIndex + 2] = B;
            imageData.data[pixelIndex + 3] = 255; // Alpha (불투명)
        }
        ctx.putImageData(imageData, 0, 0);
    }

    // 서버로부터 'map_update' 이벤트를 수신하면 drawMap 함수를 호출합니다.
    socket.on('map_update', (mapData) => {
        // console.log('New map data received'); // 디버깅용
        drawMap(mapData);
    });

    console.log('Map renderer initialized and waiting for map data...');
});
