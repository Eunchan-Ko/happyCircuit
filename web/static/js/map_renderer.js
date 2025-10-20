document.addEventListener('DOMContentLoaded', () => {
    const canvas = document.getElementById('mapCanvas');
    // 이 스크립트는 map.html에서만 로드되므로 canvas가 항상 존재합니다.
    const ctx = canvas.getContext('2d');

    /**
     * 서버로부터 받은 지도 데이터를 Canvas에 그리는 함수
     * @param {object} mapData - /api/get_map으로부터 받은 JSON 데이터
     */
    function drawMap(mapData) {
        const { width, height, data } = mapData;
        canvas.width = width;
        canvas.height = height;
        const imageData = ctx.createImageData(width, height);

        for (let i = 0; i < data.length; i++) {
            const x = i % width;
            const y = height - 1 - Math.floor(i / width);
            const pixelIndex = (y * width + x) * 4;

            let R, G, B;
            const value = data[i];
            if (value === -1) { [R, G, B] = [128, 128, 128]; } // 회색
            else if (value === 0) { [R, G, B] = [255, 255, 255]; } // 흰색
            else { [R, G, B] = [0, 0, 0]; } // 검은색

            imageData.data[pixelIndex] = R;
            imageData.data[pixelIndex + 1] = G;
            imageData.data[pixelIndex + 2] = B;
            imageData.data[pixelIndex + 3] = 255;
        }
        ctx.putImageData(imageData, 0, 0);
    }

    /**
     * 주기적으로 지도 데이터를 서버에 요청하고 화면을 갱신하는 함수
     */
    async function fetchAndUpdateMap() {
        try {
            const response = await fetch('/api/get_map');
            if (!response.ok) {
                console.error('지도 데이터 가져오기 실패:', response.statusText);
                return;
            }
            const mapData = await response.json();
            if (mapData.error) {
                console.error('서버 오류:', mapData.error);
                return;
            }
            drawMap(mapData);
        } catch (error) {
            console.error('지도 데이터 요청 중 오류 발생:', error);
        }
    }

    // 2초마다 지도를 새로고침합니다.
    setInterval(fetchAndUpdateMap, 2000);
    // 페이지 로드 시 첫 지도를 바로 표시
    fetchAndUpdateMap();
});