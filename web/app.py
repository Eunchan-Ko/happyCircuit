from flask import Flask, render_template, jsonify
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/status')
def status():
     # TODO : if raspberryPi can enable, edit this code
     pi_cv_connected = True
     pi_slam_connected = True

     return jsonify({
         "pi_cv": {
             "connected": pi_cv_connected,
             "status": "OpenCV 단선 검사 준비됨" if pi_cv_connected else "연결 안됨"
         },
         "pi_slam": {
             "connected": pi_slam_connected,
             "status": "SLAM 및 하드웨어 제어 준비됨" if pi_slam_connected else "연결 안됨"
         }
     })

if __name__ == '__main__':
    app.run(debug=True)
