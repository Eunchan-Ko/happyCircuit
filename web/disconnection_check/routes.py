from flask import Blueprint, render_template, current_app
import pymongo

# Blueprint 정의
disconnection_check_bp = Blueprint('disconnection_check', __name__, template_folder='templates')

@disconnection_check_bp.route('/disconnection_check')
def disconnection_check_page():
    """
    DB 연결 상태에 따라 저장된 경고를 표시하거나, 
    순찰을 먼저 진행하라는 메시지를 표시하는 페이지를 렌더링합니다.
    """
    # app.config에서 DB 정보 가져오기
    db_connected = current_app.config.get('DB_CONNECTED', False)
    warnings_collection = current_app.config.get('WARNINGS_COLLECTION')

    warnings = []
    if db_connected and warnings_collection is not None:
        # DB에서 모든 경고를 시간 내림차순으로 조회합니다.
        try:
            warnings = list(warnings_collection.find().sort("timestamp", pymongo.DESCENDING))
        except Exception as e:
            # 로깅을 위해 print 대신 로거 사용을 권장합니다.
            print(f"Error fetching warnings from DB: {e}")
            # 에러 발생 시 db_connected를 False로 간주하여 처리
            return render_template('disconnection_check.html', db_connected=False, warnings=[])

    return render_template('disconnection_check.html', db_connected=db_connected, warnings=warnings)
