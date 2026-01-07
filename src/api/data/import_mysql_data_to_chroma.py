"""
导入邮件数据到Chroma向量数据库API
路径: src/api/data/import_mysql_data_to_chroma.py
接口: POST /api/data/import_chroma
"""

from sentence_transformers import SentenceTransformer
import chromadb
import json
import os
import sys
from flask import Blueprint, request, jsonify

# 添加项目根目录到Python路径
current_file = os.path.abspath(__file__)
data_dir = os.path.dirname(current_file)
api_dir = os.path.dirname(data_dir)
src_dir = os.path.dirname(api_dir)
project_root = os.path.dirname(src_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.logger import logger
from data.db_init import get_db_connection

# 创建蓝图
import_chroma_bp = Blueprint('import_chroma', __name__)

@import_chroma_bp.route('/import_chroma', methods=['POST'])
def import_chroma():
    """
    导入邮件数据到Chroma向量数据库API
    """
    try:
        # ======================
        # 1. 加载 MySQL 数据
        # ======================
        logger.info("正在连接MySQL...")
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT 
            id,
            email_id,
            subject,
            content_text,
            url_list,
            label
        FROM email_data
        WHERE content_text IS NOT NULL
        LIMIT 1000
        """)

        rows = cursor.fetchall()
        
        if not rows:
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': '没有找到可导入的邮件数据'
            }), 400

        logger.info(f"✅ 从MySQL读取 {len(rows)} 条记录")

        # ======================
        # 2. 初始化 embedding 模型
        # ======================
        logger.info("正在加载 embedding 模型...")
        
        local_model_path = os.path.join(project_root, "data", "bge-small")
        logger.info(f"使用本地模型: {local_model_path}")
        
        try:
            model = SentenceTransformer(local_model_path)
            logger.info("✅ embedding模型加载成功")
        except Exception as model_error:
            logger.error(f"❌ 模型加载失败: {str(model_error)}", exc_info=True)
            cursor.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': f'模型加载失败: {str(model_error)}'
            }), 500

        # ======================
        # 3. 初始化 Chroma
        # ======================
        logger.info("正在初始化 Chroma...")
        chroma_path = os.path.join(project_root, "chroma_db")
        os.makedirs(chroma_path, exist_ok=True)
        
        client = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_or_create_collection(
            name="email_knowledge_base",
            metadata={"hnsw:space": "cosine","dimension": 384}
        )
        logger.info("✅ Chroma初始化成功")

        # ======================
        # 4. 批量处理和写入 Chroma
        # ======================
        logger.info(f"开始处理 {len(rows)} 条邮件数据...")
        
        documents = []
        embeddings = []
        metadatas = []
        ids = []
        error_count = 0
        batch_size = 50

        for idx, row in enumerate(rows, 1):
            try:
                # row 是字典，用字段名访问
                row_id = row['id']
                email_id = row['email_id']
                subject = row['subject'] or ""
                content_text = row['content_text'] or ""
                url_list = row['url_list']
                label = row['label']

                # 解析URL列表（JSON字符串）
                try:
                    urls = json.loads(url_list) if url_list else []
                except (json.JSONDecodeError, TypeError):
                    urls = []

                url_text = "\n".join(urls) if isinstance(urls, list) else str(urls)

                # 拼接文档内容
                document_text = f"""Subject: {subject}

Content:
{content_text}

URLs:
{url_text}"""

                # 生成向量
                embedding = model.encode(document_text).tolist()

                documents.append(document_text)
                embeddings.append(embedding)
                metadatas.append({
                    "email_id": str(email_id),
                    "label": str(label),
                })
                ids.append(str(email_id))

                # 每batch_size条记录写入一次
                if len(documents) >= batch_size:
                    logger.info(f"写入批次: {len(documents)} 条记录")
                    collection.add(
                        documents=documents,
                        embeddings=embeddings,
                        metadatas=metadatas,
                        ids=ids
                    )
                    documents = []
                    embeddings = []
                    metadatas = []
                    ids = []

            except Exception as row_error:
                logger.warning(f"⚠️ 第 {idx} 条记录处理失败: {str(row_error)}", exc_info=True)
                error_count += 1
                continue

        # 写入剩余数据
        if documents:
            logger.info(f"写入最后批次: {len(documents)} 条记录")
            collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )

        total_imported = len(rows) - error_count
        logger.info(f"✅ 导入完成！成功: {total_imported} 条，失败: {error_count} 条")

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'total': total_imported,
            'failed': error_count,
            'message': f'成功写入 {total_imported} 条邮件向量到Chroma！'
        }), 200

    except Exception as e:
        logger.error(f"❌ 导入Chroma失败: {str(e)}", exc_info=True)
        try:
            cursor.close()
            conn.close()
        except:
            pass
        return jsonify({
            'success': False,
            'message': f'导入失败: {str(e)}'
        }), 500