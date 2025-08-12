import cv2
from flask import Flask, Response, render_template_string
from ultralytics import YOLO
import sys

# --- Configuration ---
# Raspberry Pi's MJPEG stream URL
RPI_STREAM_URL = 'http://[YOUR_RASPBERRY_PI_IP]:5000/video_feed'

# Port for the personal computer's web server
PC_SERVER_PORT = 5001

# Path to your NCNN YOLO model on the personal computer
MODEL_PATH = "/home/your_user/best_reversion_ncnn_model"

# --- Flask App Setup ---
app = Flask(__name__)

# Load the NCNN YOLO model on the personal computer
try:
    model = YOLO(MODEL_PATH, task='detect')
    class_names = model.names
    warning_class_index = -1
    for idx, name in class_names.items():
        if name == 'warning':
            warning_class_index = idx
            break
except Exception as e:
    print(f"Error loading model: {e}")
    sys.exit(1)

# Function to generate the MJPEG stream
def gen_frames():
    # Capture MJPEG stream from the Raspberry Pi
    cap = cv2.VideoCapture(RPI_STREAM_URL)

    if not cap.isOpened():
        print(f"Error: Could not open video stream from {RPI_STREAM_URL}.")
        return

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Could not read frame from stream. Reconnecting...")
            cap = cv2.VideoCapture(RPI_STREAM_URL)
            if not cap.isOpened():
                print("Failed to reconnect.")
                break
            continue
        
        # Perform YOLO inference on the frame
        results = model(frame, verbose=False)
        
        # Get the annotated frame from the results
        annotated_frame = results[0].plot()
        boxes = results[0].boxes

        error_message = ""
        # Check for confidence scores above 0.7 for the 'warning' class
        if warning_class_index != -1:
            for box in boxes:
                if box.cls == warning_class_index and box.conf.item() > 0.7:
                    error_message = "ERROR Detection!"
                    break
        
        # Add the error message to the frame
        if error_message:
            cv2.putText(annotated_frame, error_message, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)
            
        # Encode the processed frame as a JPEG image
        ret, buffer = cv2.imencode('.jpg', annotated_frame)
        if not ret:
            continue

        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
    
    cap.release()

# Route to display the processed video in the web server
@app.route('/')
def index():
    return render_template_string('''
    <html>
        <head><title>YOLO Inference on PC</title></head>
        <body>
            <h1>Processed Stream from Raspberry Pi</h1>
            <img src="/video_feed" width="640" height="480">
        </body>
    </html>
    ''')

# Route to provide the MJPEG stream
@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# Main entry point of the script
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PC_SERVER_PORT)

