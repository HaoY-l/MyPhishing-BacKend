import json
import os
import sys
from flask import Blueprint, request, jsonify

# 项目根路径配置
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 创建蓝图（添加URL前缀，确保接口路径是 /api/web/setting）
setting_data_bp = Blueprint('setting', __name__, url_prefix='/api/web')

# 配置文件路径（唯一数据源）
CONFIG_PATH = os.path.join(project_root, 'config/config.json')

# --------------------------
# 工具函数：仅确保配置文件目录存在
# --------------------------
def ensure_config_dir_exists():
    """仅创建配置目录，不创建/修改任何文件内容"""
    config_dir = os.path.dirname(CONFIG_PATH)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

# --------------------------
# 定义默认配置（所有开关开启）
# --------------------------
DEFAULT_CONFIG = {
    "EMAIL_INTERCEPT_ENABLED_1": True,  # 可疑邮件拦截开启
    "EMAIL_ALERT_ENABLED_1": True,      # 可疑邮件告警开启
    "EMAIL_INTERCEPT_ENABLED_2": True,  # 恶意邮件拦截开启
    "EMAIL_ALERT_ENABLED_2": True,      # 恶意邮件告警开启
    "NOTIFICATION_EMAIL": ""            # 告警通知邮箱（默认为空）
}

# --------------------------
# 统一返回格式工具函数（适配前端code格式）
# --------------------------
def api_response(code, message, data=None):
    """
    适配前端request.js的返回格式：
    {
        "code": 200/404/500,  // 200成功，其他失败
        "message": "提示信息",
        "data": 数据对象
    }
    """
    return jsonify({
        "code": code,
        "message": message,
        "data": data or {}
    })

# --------------------------
# GET /api/web/setting - 获取配置（完全读取文件内容）
# --------------------------
@setting_data_bp.route('/setting', methods=['GET'])
def get_setting():
    """仅读取配置文件原始内容，无任何字段过滤/添加"""
    try:
        ensure_config_dir_exists()
        
        # 配置文件不存在时，创建并写入默认配置（首次访问自动初始化）
        if not os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
            return api_response(200, "配置文件初始化成功（默认全部开启）", DEFAULT_CONFIG)
        
        # 读取配置文件原始内容
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 返回文件原始内容
        return api_response(200, "配置获取成功", config)
    
    except json.JSONDecodeError:
        return api_response(500, "配置文件格式错误，请检查JSON语法"), 500
    except Exception as e:
        return api_response(500, f"读取配置失败：{str(e)}"), 500

# --------------------------
# POST /api/web/setting - 修改配置（完全动态处理）
# --------------------------
@setting_data_bp.route('/setting', methods=['POST'])
def set_setting():
    """
    完全动态处理配置更新：
    1. 恢复默认 = 所有开关开启
    2. 仅更新配置文件中已存在的字段
    3. 正确处理布尔值和字符串字段
    """
    try:
        ensure_config_dir_exists()
        
        # 获取前端提交的数据
        request_data = request.get_json() or {}
        
        # 1. 处理恢复默认操作
        if request_data.get('action') == 'reset':
            # 写入默认配置（所有开关开启）
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
            return api_response(200, "已恢复默认配置（所有开关开启）", DEFAULT_CONFIG)
        
        # 配置文件不存在时，先初始化默认配置
        if not os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
            current_config = DEFAULT_CONFIG.copy()
        else:
            # 读取现有配置
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                current_config = json.load(f)
        
        # 2. 动态更新配置（区分布尔字段和字符串字段）
        # 定义布尔字段列表
        BOOL_FIELDS = [
            'EMAIL_INTERCEPT_ENABLED_1',
            'EMAIL_ALERT_ENABLED_1', 
            'EMAIL_INTERCEPT_ENABLED_2',
            'EMAIL_ALERT_ENABLED_2'
        ]
        
        for field, value in request_data.items():
            # 跳过action字段
            if field == 'action':
                continue
            
            # 仅当字段存在于配置文件中时才更新
            if field in current_config:
                # 布尔字段处理
                if field in BOOL_FIELDS:
                    try:
                        if isinstance(value, str):
                            value = value.lower() == 'true'
                        current_config[field] = bool(value)
                    except:
                        current_config[field] = value
                # 字符串字段处理（如 NOTIFICATION_EMAIL）
                else:
                    current_config[field] = str(value) if value else ""
        
        # 3. 写入配置文件
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(current_config, f, indent=2, ensure_ascii=False)
        
        # 4. 返回更新后的配置
        return api_response(200, "配置更新成功", current_config)
    
    except json.JSONDecodeError:
        return api_response(500, "配置文件格式错误，无法更新"), 500
    except Exception as e:
        return api_response(500, f"更新配置失败：{str(e)}"), 500