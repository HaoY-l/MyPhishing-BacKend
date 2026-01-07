from flask import request, jsonify
from .service import license_service

# 白名单 - 不需要授权检查的路径
LICENSE_WHITELIST = [
    '/api/utils/machine-id',
    '/api/utils/status',
    '/api/utils/activate',
    '/api/web/setting',
    '/api/web/vectordata',
    '/api/web/emaildata',
    '/api/web/dashboard',
]


def is_path_in_whitelist(path):
    """
    判断路径是否在白名单中
    :param path: 请求路径
    :return: bool
    """
    # 去除查询参数，只保留路径部分
    path = path.split('?')[0]
    
    # 精确匹配白名单
    for whitelist_path in LICENSE_WHITELIST:
        if path == whitelist_path:
            return True
    
    return False


def check_license():
    """
    授权检查中间件
    在每个请求前执行，检查是否已授权
    """
    # 获取当前请求路径
    current_path = request.path
    
    # 跨域预检请求直接放行
    if request.method == 'OPTIONS':
        return None
    
    # 检查是否在白名单中
    if is_path_in_whitelist(current_path):
        return None  # 白名单路径，放行
    
    # 不在白名单，检查授权状态
    if not license_service.is_licensed():
        # 未授权，获取详细状态信息
        status = license_service.get_license_status()
        
        return jsonify({
            'code': 403,
            'message': '未授权或授权已过期，请先激活授权',
            'data': status
        }), 403
    
    # 已授权，放行
    return None


def register_license_middleware(app):
    """
    注册授权中间件到 Flask app
    :param app: Flask 应用实例
    """
    app.before_request(check_license)
    print("✓ 授权中间件已注册")