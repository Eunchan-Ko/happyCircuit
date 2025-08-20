from flask import Blueprint, render_template, request, jsonify
import os
from .image_processor import process_image_for_disconnection

# Define the blueprint for disconnection check
disconnection_check_bp = Blueprint('disconnection_check', __name__, template_folder='templates')

# --- Configuration for image processing ---
# IMPORTANT: You should create this directory and place test images inside it.
# For example: /Users/go-eunchan/HappyCircuit/test_images/
IMAGE_DIR = "/Users/go-eunchan/HappyCircuit/test_images/"

@disconnection_check_bp.route('/disconnection_check')
def disconnection_check_page():
    """Renders the disconnection check page."""
    return render_template('disconnection_check.html')

@disconnection_check_bp.route('/api/process_disconnection_images', methods=['POST'])
def process_disconnection_images():
    """
    Processes images from a predefined directory and returns the results.
    """
    if not os.path.exists(IMAGE_DIR):
        return jsonify({"error": f"Image directory not found: {IMAGE_DIR}"}), 404

    processed_results = []
    image_files = [f for f in os.listdir(IMAGE_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]

    if not image_files:
        return jsonify({"message": "No image files found in the directory."}), 200

    for filename in image_files:
        image_path = os.path.join(IMAGE_DIR, filename)
        base64_image, detected, message = process_image_for_disconnection(image_path)

        processed_results.append({
            "filename": filename,
            "image_data": base64_image,
            "disconnection_detected": detected,
            "message": message
        })
    
    return jsonify(processed_results), 200
