from flask import Blueprint, jsonify, request
from .service import license_service

# 创建蓝图
license_bp = Blueprint('license', __name__)


@license_bp.route('/machine-id', methods=['GET'])
def get_machine_id():
    """获取机器码"""
    try:
        machine_id = license_service.get_machine_id()
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': {
                'machine_id': machine_id
            }
        })
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'获取机器码失败: {str(e)}'
        }), 500


@license_bp.route('/status', methods=['GET'])
def get_status():
    """获取授权状态"""
    try:
        status = license_service.get_license_status()
        return jsonify({
            'code': 200,
            'message': 'success',
            'data': status
        })
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'获取授权状态失败: {str(e)}'
        }), 500


@license_bp.route('/activate', methods=['POST'])
def activate():
    """激活授权码"""
    try:
        data = request.get_json()
        
        if not data or 'license_code' not in data:
            return jsonify({
                'code': 400,
                'message': '请提供授权码'
            }), 400
        
        license_code = data['license_code'].strip()
        
        if not license_code:
            return jsonify({
                'code': 400,
                'message': '授权码不能为空'
            }), 400
        
        # 激活授权
        success, result = license_service.activate_license(license_code)
        
        if success:
            return jsonify({
                'code': 200,
                'message': '授权激活成功',
                'data': result
            })
        else:
            return jsonify({
                'code': 400,
                'message': result
            }), 400
            
    except Exception as e:
        return jsonify({
            'code': 500,
            'message': f'激活授权失败: {str(e)}'
        }), 500