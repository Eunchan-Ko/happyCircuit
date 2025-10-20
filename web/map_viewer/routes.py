from flask import Blueprint, render_template

map_bp = Blueprint('map_viewer', __name__, template_folder='../templates')

# ✨ 이 라우트가 /map URL을 처리하도록 수정합니다.
@map_bp.route('/map')
def show_map_page():
    """
    /map URL 요청 시, base.html을 상속받은 map.html 페이지를 렌더링합니다.
    """
    return render_template('map.html')
