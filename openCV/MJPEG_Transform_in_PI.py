from picamera2 import Picamera2
import cv2

# Initialize the Picamera2
picam2 = Picamera2()
picam2.preview_configuration.main.size = (1280, 720)
picam2.preview_configuration.main.format = "RGB888"
picam2.preview_configuration.align()
picam2.configure("preview")
picam2.start()

# This function captures video frames from the Raspberry Pi camera
# and converts them into an MJPEG stream format. It does NOT perform inference.
def gen_frames():
    while True:
        # Capture frame-by-frame
        frame = picam2.capture_array("main")

        # Encode the frame as a JPEG image
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue

        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
