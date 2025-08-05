from flask import Blueprint, render_template

# 1. 'control'이라는 이름의 블루프린트 객체를 생성합니다.
#    'control' : 블루프린트의 별명
#    __name__ : 현재 파일의 위치를 알려줌
#    template_folder='templates' : 이 블루프린트가 사용할 템플릿 폴더의 위치 (여기서는 사용하지 않지만 기본 구조)
control_bp = Blueprint('control', __name__, template_folder='templates')


# 2. @app.route 대신 @control_bp.route를 사용하여 라우트를 정의합니다.
@control_bp.route('/control')
def control_page():
    """/control URL에 접속했을 때 control.html 파일을 렌더링합니다."""
    return render_template('control.html')
