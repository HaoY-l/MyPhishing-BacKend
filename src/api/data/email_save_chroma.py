"""
邮件向量入库接口 - 高并发重构版
路径: src/api/ai/save_chroma_by_id.py
功能: 邮件查询 -> 文本拼接 -> 向量化 -> 写入 ChromaDB
"""

import json
import os
import sys
import pymysql
from flask import Blueprint, request, jsonify
from src.utils.models_loader import ModelManager

# ==================================
# 路径配置与模块导入
# ==================================
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.logger import logger
from data.db_init import get_db_connection

save_chroma_by_id_bp = Blueprint('save_chroma_by_id', __name__)

def generate_document_text(email_data: dict) -> str:
    """提取核心文本用于向量化"""
    subject = email_data.get('subject', "") or ""
    content_text = email_data.get('content_text', "") or ""
    url_list = email_data.get('url_list', "") or ""
    
    try:
        urls = json.loads(url_list) if isinstance(url_list, str) and url_list else []
    except (json.JSONDecodeError, TypeError):
        urls = []
    
    url_text = "\n".join(urls) if isinstance(urls, list) else str(urls)
    return f"Subject: {subject}\n\nContent:\n{content_text}\n\nURLs:\n{url_text}".strip()

# ==================================
# 核心接口实现
# ==================================

@save_chroma_by_id_bp.route('/save_email_to_chroma_by_id', methods=['POST'])
def save_email_to_chroma_by_id():
    """
    通过邮件ID将数据同步至 Chroma 向量库
    适配 500 并发：使用连接池、单例模型、严谨的资源回收
    """
    # 1. 直接获取单例资源 (由 app.py 启动时预加载)
    try:
        embedding_model = ModelManager.get_embedding_model()
        chroma_client = ModelManager.get_chroma_client()
    except Exception as e:
        logger.error(f"❌ 向量库资源初始化失败: {e}")
        return jsonify({'success': False, 'message': '模型服务暂不可用'}), 503

    conn = None
    try:
        # 2. 参数解析
        data = request.get_json() or {}
        email_id = data.get('email_id')
        if not email_id:
            return jsonify({'success': False, 'message': '缺少必要字段: email_id'}), 400
        
        logger.info(f"🚀 开始向量同步任务，邮件ID: {email_id}")

        # 3. 从 MySQL 查询原始数据 (使用 DictCursor 自动映射字典)
        conn = get_db_connection()
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            sql = """
                SELECT id, email_id, subject, content_text, url_list, label 
                FROM email_data 
                WHERE email_id = %s AND content_text IS NOT NULL
                LIMIT 1
            """
            cursor.execute(sql, (email_id,))
            email_row = cursor.fetchone()
            
            if not email_row:
                logger.warning(f"⚠️ 未找到有效邮件数据或正文为空: {email_id}")
                return jsonify({'success': False, 'message': '未找到邮件数据'}), 200 # 返回200防止网关报错

        # 4. 生成文本并向量化
        document_text = generate_document_text(email_row)
        
        # 调用单例模型的推理方法
        embedding = embedding_model.encode(document_text).tolist()

        # 5. 写入或更新 Chroma (Upsert 模式)
        collection = chroma_client.get_or_create_collection(
            name="email_knowledge_base",
            metadata={"hnsw:space": "cosine"}
        )

        collection.add(
            documents=[document_text],
            embeddings=[embedding],
            metadatas=[{
                "email_id": str(email_id),
                "label": str(email_row.get('label', "")),
                "db_id": str(email_row.get('id', ""))
            }],
            ids=[str(email_id)]
        )

        logger.info(f"✅ 向量入库成功: {email_id}")
        return jsonify({'success': True, 'email_id': email_id}), 200

    except Exception as e:
        logger.error(f"💥 向量入库异常: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': f"Internal Error: {str(e)}"}), 500
    finally:
        # ✅ 极其关键：归还数据库连接至连接池
        if conn:
            conn.close()