from flask import Blueprint


# 创建主 API 蓝图
api_bp = Blueprint("api", __name__, url_prefix="/api")

# 注册所有子蓝图
from .data.import_spam_data_to_mysql import import_spam_bp
api_bp.register_blueprint(import_spam_bp, url_prefix="/data")

from .data.import_mysql_data_to_chroma import import_chroma_bp
api_bp.register_blueprint(import_chroma_bp, url_prefix="/data")

from .data.query_chroma_api import query_chroma_bp
api_bp.register_blueprint(query_chroma_bp, url_prefix="/data")

from .data.query_email import query_email_bp
api_bp.register_blueprint(query_email_bp, url_prefix="/data")

from .email.email_save import save_email_bp
api_bp.register_blueprint(save_email_bp, url_prefix="/email")

from .threat.threat_intel_query import threat_query_bp
api_bp.register_blueprint(threat_query_bp, url_prefix="/threat")

from .threat.sandbox_query import sandbox_query_bp
api_bp.register_blueprint(sandbox_query_bp, url_prefix="/threat")

from .ai.info_to_vector import vectorize_bp
api_bp.register_blueprint(vectorize_bp, url_prefix="/ai")

from .ai.deepseek import ai_bp
api_bp.register_blueprint(ai_bp, url_prefix="/ai")

from .data.email_save_chroma import save_chroma_by_id_bp
api_bp.register_blueprint(save_chroma_by_id_bp, url_prefix="/data")


from .web.web_data import web_dashboard_bp
api_bp.register_blueprint(web_dashboard_bp, url_prefix="/web")

from .web.web_email_data import web_email_data_bp
api_bp.register_blueprint(web_email_data_bp, url_prefix="/web")

from .web.web_vector_data import vector_data_bp
api_bp.register_blueprint(vector_data_bp, url_prefix="/web")

from .web.web_ai_data import ai_data_bp
api_bp.register_blueprint(ai_data_bp, url_prefix="/web")

from .web.web_setting_data import setting_data_bp
api_bp.register_blueprint(setting_data_bp, url_prefix="/web")

from .utils import license_bp
api_bp.register_blueprint(license_bp, url_prefix="/utils")