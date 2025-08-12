from ultralytics import YOLO
from picamera2 import Picamera2
import cv2

# Initialize the Picamera2
picam2 = Picamera2()
picam2.preview_configuration.main.size = (1280, 720)
picam2.preview_configuration.main.format = "RGB888"
picam2.preview_configuration.align()
picam2.configure("preview")
picam2.start()

ncnn_model = YOLO("/home/pi/best_reversion_ncnn_model",task='detect')

def gen_frames():
    while True:
        # Capture frame-by-frame
        frame = picam2.capture_array("main")

        # Run YOLO inference on the frame
        results = ncnn_model(frame)
        
        class_names = results[0].names
        warning_class_index = -1
        for idx, name in class_names.items():
            if name == 'warning':
                warning_class_index = idx
                break
				
        # Visualize the results on the frame
        annotated_frame = results[0].plot()
        boxes = results[0].boxes

        
        error_message = ""
        if warning_class_index != -1:
            for box in boxes:
                if box.cls == warning_class_index and box.conf.item() > 0.7:
                    error_message = "ERROR Detection!"
                    break
        
        if error_message:
            cv2.putText(annotated_frame, error_message, (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2, cv2.LINE_AA)
        
        ret, buffer = cv2.imencode('.jpg', annotated_frame)
        if not ret:
            continue  # ? now legal, because it's inside a while loop

        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

