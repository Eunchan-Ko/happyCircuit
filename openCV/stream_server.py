from flask import Flask, render_template, Response
from cable_check import gen_frames

app = Flask(__name__)

@app.route('/')
def index():
    return '''
    <html>
        <head><title>YOLO Realtime-dectection</title></head>
        <body>
            <h1>YOLO NCNN Realtime streaming</h1>
            <img src="/video_feed" width="640" height="480">
        </body>
    </html>
    '''

@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
