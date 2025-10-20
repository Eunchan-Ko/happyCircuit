from flask import Blueprint, render_template, jsonify, current_app
import os
import json

map_viewer_bp = Blueprint('map_viewer', __name__)

# ✨ 이 라우트가 /map URL을 처리하도록 수정합니다.
@map_bp.route('/map')
def show_map_page():
    """
    /map URL 요청 시, base.html을 상속받은 map.html 페이지를 렌더링합니다.
    """
    return render_template('map.html')

@map_bp.route('/api/get_map')
def get_map_data():
    """
    저장된 map.json 파일의 내용을 읽어 API 형태로 반환합니다.
    프론트엔드 JavaScript가 이 주소를 주기적으로 호출할 것입니다.
    """
    # static 폴더의 절대 경로를 기반으로 파일 경로를 동적으로 생성
    static_folder = current_app.static_folder
    map_file_path = os.path.join(static_folder, 'map', 'map.json')

    try:
        with open(map_file_path, 'r') as f:
            data = json.load(f)
        return jsonify(data)
    except FileNotFoundError:
        return jsonify({'error': '지도 파일을 찾을 수 없습니다. ROS의 map_saver_node가 실행 중인지 확인하세요.'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500