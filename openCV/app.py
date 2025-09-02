# app.py
from flask import Flask, Response, request, render_template_string
import cv2
import time
import os
from ultralytics import YOLO

# ===== 설정 =====
RTSP_URL   = "rtsp://127.0.0.1:8554/cam?tcp"
MODEL_PATH = "models/best_updated.pt" # 모델 파일명
IMG_SIZE   = 640                  # 512~640 권장
CONF_THRES = 0.40                 # 신뢰도 임계값
SHOW_ONLY_DAMAGE = True          # True=손상 계열만 표시, False=모든 클>DAMAGE_KEYWORDS = ["damage", "damaged", "defect", "broken", "fail"]

# (보안) 토큰 방식의 아주 단순한 인증
# 환경변수 APP_TOKEN 을 우선 사용, 없으면 하드코드 값
APP_TOKEN = os.environ.get("APP_TOKEN", "00000000")

# ===== 앱/모델 =====
app = Flask(__name__)
model = YOLO(MODEL_PATH)          # GPU 있으면 자동 사용
names = model.names if hasattr(model, "names") else {}

# damage 계열 클래스 인덱스 자동 탐색
damage_class_idxs = []
if SHOW_ONLY_DAMAGE and names:
    try:
        # names 가 dict 또는 list 인 모든 경우 처리
        iterable = names.items() if isinstance(names, dict) else enumer>        for idx, name in iterable:
            lname = str(name).lower()
            if any(k in lname for k in DAMAGE_KEYWORDS):
                damage_class_idxs.append(int(idx))
    except Exception as e:
        print("[WARN] damage 라벨 탐색 중 예외:", e)
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b">
# ===== 간단 인증 (토큰) =====
@app.before_request
def simple_auth():
    # 홈/헬스체크는 열어두고, 나머지는 토큰 검사
    if request.path in ("/", "/health"):
        return None
    token = request.args.get("token")
    if token != APP_TOKEN:
        return Response("Unauthorized", status=401)

# ===== 라우트 =====
@app.route("/")
def index():
    # 편의상 링크 제공(여기 문자열의 token 값을 실제 비밀번호로 바꿔서 >    return render_template_string("""
    <h3>RTSP→YOLO→Flask 데모</h3>
    <p><a href="/video?token={{token}}">/video 열기</a></p>
    """, token=APP_TOKEN)

@app.route("/health")
def health():
    return "OK"

@app.route("/video")
def video():
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundar>
if __name__ == "__main__":                                                  # Ultralytics 경고 제거용(선택)
    os.makedirs(os.path.expanduser("~/.config/Ultralytics"), exist_ok=T>    os.environ.setdefault("YOLO_CONFIG_DIR", os.path.expanduser("~/.con>
    app.run(host="0.0.0.0", port=8080, threaded=True)
