"""
AI分析数据统一查询API
路径: src/api/web/ai_data_api.py
接口: POST /api/web/aidata
功能: 适配前端AI分析模块的数据展示需求
    - 封装/api/ai/aichat接口的返回数据
    - 格式化数据结构，适配前端展示
    - 对接真实8000端口后端，无模拟数据
"""

import os
import sys
import json
from flask import Blueprint, request, jsonify
import requests

# 项目根路径配置
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入工具模块
from src.utils.logger import logger

# 创建蓝图
ai_data_bp = Blueprint('ai_data', __name__)

# ==================== 真实接口配置 =====================
# AI分析核心接口地址（8000端口）
AI_CHAT_API_URL = "http://localhost:8000/api/ai/aichat"

# ==============================================================================
# 核心接口：/api/web/aidata
# 仅保留前端AI分析所需的核心功能，无其他冗余接口
# ==============================================================================

@ai_data_bp.route('/aidata', methods=['POST'])
def get_ai_data():
    """
    AI分析数据统一接口：适配前端展示的AI分析数据
    - 纯真实数据，无模拟
    - 封装调用8000端口的/api/ai/aichat接口
    - 格式化数据结构，便于前端直接使用
    
    POST 请求体:
    {
        "email_id": "xxx",          // 邮件ID（必填/选填）
        "email_text": "xxx"         // 邮件文本内容（可选）
    }
    """
    try:
        # --- 1. 获取并校验请求参数 ---
        request_data = request.get_json() or {}
        email_id = request_data.get('email_id', '').strip()
        email_text = request_data.get('email_text', '').strip()
        
        # 参数校验
        if not email_id and not email_text:
            logger.warning("请求参数为空：email_id和email_text均未提供")
            return jsonify({
                'code': 400,
                'success': False,
                'message': '参数错误：email_id 或 email_text 必须提供一个'
            }), 400
        
        # --- 2. 调用8000端口的AI分析核心接口 ---
        ai_chat_params = {
            "email_id": email_id,
            "email_text": email_text
        }
        
        logger.info(f"调用8000端口AI分析接口: {AI_CHAT_API_URL}, 参数: {ai_chat_params}")
        
        # 调用真实后端接口
        response = requests.post(
            AI_CHAT_API_URL,
            json=ai_chat_params,
            timeout=60,
            headers={
                "Content-Type": "application/json"
            }
        )
        
        # 校验响应状态
        if response.status_code != 200:
            logger.error(
                f"AI分析接口调用失败，状态码: {response.status_code}, "
                f"响应内容: {response.text[:500]}"
            )
            return jsonify({
                'code': response.status_code,
                'success': False,
                'message': f'AI分析接口调用失败: {response.reason}',
                'detail': response.text[:500]
            }), response.status_code
        
        # 解析返回数据
        ai_chat_result = response.json()
        logger.info(f"AI分析接口返回数据: {json.dumps(ai_chat_result)[:1000]}")
        
        # --- 3. 格式化数据（适配前端展示）---
        if ai_chat_result.get('code') == 200 and ai_chat_result.get('data'):
            raw_data = ai_chat_result['data']
            ai_analysis = raw_data.get('ai_analysis', {})
            
            # 前端所需的核心数据结构
            formatted_result = {
                # AI分析核心结果（前端直接展示的字段）
                "riskLevel": ai_analysis.get('result'),          # 0=安全 1=可疑 2=恶意
                "confidence": ai_analysis.get('confidence'),     # 置信度
                "phishType": ai_analysis.get('phishing_type'),   # 钓鱼类型
                "reason": ai_analysis.get('reason')              # 分析理由
            }
            
            # --- 4. 返回格式化数据 ---
            return jsonify({
                'code': 200,
                'success': True,
                'message': ai_chat_result.get('message', 'AI分析完成'),
                'data': formatted_result
            })
        
        else:
            # 接口返回异常处理
            logger.error(f"AI分析接口返回数据异常: {ai_chat_result}")
            return jsonify({
                'code': ai_chat_result.get('code', 500),
                'success': False,
                'message': ai_chat_result.get('message', 'AI分析失败'),
                'data': {}
            }), ai_chat_result.get('code', 500)
        
    except requests.exceptions.RequestException as e:
        # 网络异常处理
        logger.error(f"调用8000端口AI分析接口网络异常: {str(e)}", exc_info=True)
        return jsonify({
            'code': 503,
            'success': False,
            'message': f'AI分析接口连接失败: {str(e)}',
            'error_type': type(e).__name__
        }), 503
        
    except Exception as e:
        # 未知异常处理
        logger.error(f"AI数据处理异常: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,
            'success': False,
            'message': f'服务器内部错误：{str(e)}',
            'error_detail': str(e)
        }), 500