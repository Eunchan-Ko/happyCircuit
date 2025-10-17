import cv2
from ultralytics import YOLO
import numpy as np
import os
import base64

# Path to your NCNN YOLO model
# Ensure this path is correct for your local server setup
MODEL_PATH = "/Users/go-eunchan/HappyCircuit/openCV/best_updated.pt"

# Load the YOLO model
try:
    model = YOLO(MODEL_PATH, task='detect')
    class_names = model.names
    WARNING_CLASS_INDEX = -1
    for idx, name in class_names.items():
        if name == 'warning':
            WARNING_CLASS_INDEX = idx
            break
    if WARNING_CLASS_INDEX == -1:
        print(f"Warning: 'warning' class not found in model names: {class_names}")
except Exception as e:
    print(f"Error loading YOLO model from {MODEL_PATH}: {e}")
    model = None # Set model to None if loading fails

def process_image_for_disconnection(image_path, confidence_threshold=0.9):
    """
    Loads an image, performs YOLO inference, and checks for 'warning' class
    with a confidence score above the threshold. Returns the annotated image
    as a base64 string and a boolean indicating disconnection status.
    """
    if model is None:
        return None, False, "Model not loaded."

    if not os.path.exists(image_path):
        return None, False, f"Image file not found: {image_path}"

    try:
        frame = cv2.imread(image_path)
        if frame is None:
            return None, False, f"Could not read image: {image_path}"

        results = model(frame, verbose=False)

        disconnection_detected = False
        detection_info = []

        # Check for 'warning' class with high confidence
        if WARNING_CLASS_INDEX != -1:
            for box in results[0].boxes:
                if box.cls == WARNING_CLASS_INDEX:
                    conf = box.conf.item()
                    detection_info.append({
                        "class": class_names[int(box.cls)],
                        "confidence": round(conf, 2),
                        "bbox": [int(x) for x in box.xyxy[0].tolist()]
                    })
                    if conf > confidence_threshold:
                        disconnection_detected = True

        # Annotate the frame
        annotated_frame = results[0].plot()

        # Convert annotated frame to JPEG base64 string
        ret, buffer = cv2.imencode('.jpg', annotated_frame)
        if not ret:
            return None, False, "Could not encode annotated image."
        frame_bytes = buffer.tobytes()
        base64_image = base64.b64encode(frame_bytes).decode('utf-8')

        return base64_image, disconnection_detected, "Success"

    except Exception as e:
        return None, False, f"Error during image processing: {e}"
