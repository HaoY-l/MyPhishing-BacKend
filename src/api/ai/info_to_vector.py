"""
邮件数据向量化API - 逻辑更新版
路径: src/api/ai/email_to_vector.py
"""

import os
import sys
import json
from flask import Blueprint, request, jsonify

# ==================================
# 路径配置与模块导入
# ==================================
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.logger import logger
from src.utils.models_loader import ModelManager  # ✅ 引入模型管理器
# from data.db_init import get_db_connection      # 💡 如果需要查库则取消注释

# 创建蓝图
vectorize_bp = Blueprint('vectorize', __name__)

# ==================================
# 核心逻辑
# ==================================

def generate_document_text(data: dict) -> str:
    """从传入字段提取文本"""
    subject = data.get('subject', "") or ""
    content_text = data.get('content_text', "") or ""
    
    # 也可以在这里加上 sender 等信息增强向量效果
    document_text = f"Subject: {subject}\n\nContent:\n{content_text}"
    return document_text.strip()


@vectorize_bp.route('/email_to_vector', methods=['POST'])
def email_to_vector():
    """
    将邮件关键信息转换为向量。
    """
    # === 1. 参数检查 ===
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': '请求体不能为空'}), 400

    email_id = data.get('email_id')
    if not email_id:
        return jsonify({'success': False, 'message': '缺少必要字段: email_id'}), 400

    # === 2. 获取模型实例 (关键改动) ===
    # 移除了顶部的全局变量检测，改为通过 ModelManager 动态获取
    try:
        embedding_model = ModelManager.get_embedding_model()
    except Exception as e:
        logger.error(f"❌ 获取 Embedding 模型失败: {str(e)}")
        return jsonify({'success': False, 'message': '模型服务不可用'}), 503

    # === 3. 文本准备 ===
    # 💡 提示：如果网关传过来的 data 只有 email_id，这里需要加一个 get_email_by_id 的逻辑去查 MySQL 取正文
    document_text = generate_document_text(data)

    if not document_text:
        logger.warning(f"邮件 ID: {email_id} 的邮件文本为空，无法向量化。")
        return jsonify({
            'success': False,
            'email_id': email_id,
            'message': '文本内容为空，无法进行向量化'
        }), 400

    try:
        # === 4. 向量化推理 ===
        logger.info(f"开始向量化邮件 ID: {email_id}")
        
        # 在多进程 Gunicorn 下，这行代码现在是安全的，因为它共用 ModelManager 的单例
        vector = embedding_model.encode(document_text).tolist()
        
        logger.info(f"✅ 邮件 ID: {email_id} 向量化成功。维度: {len(vector)}")

        # === 5. 返回结果 ===
        return jsonify({
            'success': True,
            'email_id': email_id,
            'vector': vector,
            'dimension': len(vector)
        }), 200

    except Exception as e:
        logger.error(f"❌ 邮件 ID: {email_id} 向量化失败: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'email_id': email_id,
            'message': f'向量化处理失败: {str(e)}'
        }), 500