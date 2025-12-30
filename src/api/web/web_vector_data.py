"""
向量数据统一查询API
路径: src/api/web/vector_data_api.py
接口: GET /api/web/vectordata
功能: 一次性返回向量库统计信息和支持相似邮件检索
    - 仅从Chroma向量库获取数据，不查询MySQL数据库
"""

import os
import sys
import chromadb
from flask import Blueprint, request, jsonify

# 项目根路径配置
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入工具模块
from src.utils.logger import logger

# 创建蓝图
vector_data_bp = Blueprint('vector_data', __name__)

# ==============================================================================
# 统一接口：/api/web/vectordata
# ==============================================================================

@vector_data_bp.route('/vectordata', methods=['GET', 'POST'])
def get_vector_data():
    """
    统一接口：获取向量库统计信息 + 支持相似邮件检索
    - 仅从Chroma向量库获取数据，不依赖MySQL
    
    GET 请求：仅返回统计信息
    POST 请求：返回统计信息 + 检索结果
    
    POST 请求体:
    {
        "email_id": "xxx",  // 按邮件ID检索（二选一）
        "query_text": "xxx", // 按文本内容检索（二选一）
        "top_k": 10,        // 返回结果数量，默认10
        "threshold": 0.7    // 相似度阈值，默认0.7
    }
    """
    try:
        # --- 1. 获取向量库统计信息 ---
        chroma_path = os.path.join(project_root, "chroma_db")
        client = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_or_create_collection(
            name="email_knowledge_base",
            metadata={"hnsw:space": "cosine"}
        )
        
        # 统计向量总数
        total_vectors = collection.count()
        
        # 获取向量维度（从第一条记录获取）
        vector_dimension = 512  # 默认值（bge-small 模型）
        if total_vectors > 0:
            try:
                # 使用 peek 获取样本数据
                sample = collection.peek(limit=1)
                
                # 安全检查：确保有 embeddings 且不为空
                if 'embeddings' in sample:
                    embeddings = sample['embeddings']
                    if isinstance(embeddings, list) and len(embeddings) > 0:
                        first_embedding = embeddings[0]
                        if first_embedding is not None:
                            try:
                                vector_dimension = len(first_embedding)
                                logger.info(f"成功获取向量维度: {vector_dimension}")
                            except TypeError:
                                logger.warning("向量不支持 len() 操作，使用默认值")
            except Exception as e:
                logger.warning(f"获取向量维度失败: {str(e)}，使用默认值 512")
        
        stats = {
            'total_vectors': total_vectors,
            'vector_dimension': vector_dimension
        }
        
        # --- 2. 如果是 GET 请求，仅返回统计信息 ---
        if request.method == 'GET':
            return jsonify({
                'code': 200,
                'success': True,
                'message': '向量库统计信息查询成功',
                'data': {
                    'stats': stats
                }
            })
        
        # --- 3. 如果是 POST 请求，执行相似邮件检索 ---
        data = request.get_json() or {}
        email_id = data.get('email_id', '').strip()
        query_text = data.get('query_text', '').strip()
        top_k = int(data.get('top_k', 10))
        threshold = float(data.get('threshold', 0.7))
        
        # 参数校验
        if not email_id and not query_text:
            return jsonify({
                'code': 400,
                'success': False,
                'message': 'email_id 或 query_text 必须提供一个'
            }), 400
        
        search_results = []
        
        # --- 3.1 按邮件ID检索 ---
        if email_id:
            logger.info(f"按邮件ID检索: {email_id}")
            
            try:
                # 从 Chroma 获取该邮件的向量
                chroma_results = collection.get(
                    where={"email_id": email_id},
                    include=["embeddings"]
                )
                logger.info(f"Chroma 查询结果: ids数量={len(chroma_results.get('ids', []))}")
            except Exception as e:
                logger.error(f"Chroma 查询失败: {str(e)}", exc_info=True)
                raise
            
            if not chroma_results['ids']:
                # 返回 200 + 提示结果
                return jsonify({
                    'code': 200,
                    'success': True,
                    'message': f'未找到邮件ID: {email_id} 的向量数据，可能尚未完成向量化',
                    'data': {
                        'stats': stats,
                        'results': [{
                            'email_id': email_id,
                            'similarity': 0.0,
                            'distance': 0.0,
                            'content_preview': '未找到该邮件的向量数据',
                            'label': '未知'
                        }]
                    }
                }), 200
            
            # 使用该邮件的向量进行相似度检索
            query_embedding = chroma_results['embeddings'][0]
            
            similar_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,  # 保留自己，无需多获取1条
                include=["metadatas", "documents", "distances"]
            )
            
            # 过滤逻辑：仅过滤相似度低于阈值的结果，保留自己
            logger.info(f"向量搜索返回 {len(similar_results['ids'][0])} 条结果")
            for i in range(len(similar_results['ids'][0])):
                # 从向量库元数据中获取信息
                metadata = similar_results['metadatas'][0][i]
                result_email_id = metadata.get('email_id', '')
                label = metadata.get('label', '未知')
                db_id = metadata.get('db_id', '')
                
                distance = similar_results['distances'][0][i]
                similarity = 1 - distance
                document = similar_results['documents'][0][i]
                
                logger.info(f"结果{i}: email_id={result_email_id}, similarity={similarity:.4f}, threshold={threshold}")
                
                # 仅过滤相似度低于阈值的结果
                if similarity < threshold:
                    logger.info(f"相似度 {similarity:.4f} < 阈值 {threshold}，过滤")
                    continue
                
                # 构建结果（完全来自向量库）
                search_results.append({
                    'email_id': result_email_id,
                    'similarity': round(similarity, 4),
                    'distance': round(distance, 4),
                    'content_preview': document[:200] + '...' if len(document) > 200 else document,
                    'label': label,
                    'db_id': db_id  # 保留向量库中的db_id（可选）
                })
            
            logger.info(f"过滤后剩余 {len(search_results)} 条结果")
        
        # --- 3.2 按文本内容检索 ---
        elif query_text:
            logger.info(f"按文本检索: {query_text[:100]}...")
            
            from sentence_transformers import SentenceTransformer
            
            # 加载模型
            local_model_path = os.path.join(project_root, "data", "bge-small")
            model = SentenceTransformer(local_model_path)
            
            # 生成查询向量
            query_embedding = model.encode(query_text).tolist()
            
            # 向量搜索
            similar_results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["metadatas", "documents", "distances"]
            )
            
            # 格式化结果（仅来自向量库）
            for i in range(len(similar_results['ids'][0])):
                metadata = similar_results['metadatas'][0][i]
                result_email_id = metadata.get('email_id', '')
                label = metadata.get('label', '未知')
                
                distance = similar_results['distances'][0][i]
                similarity = 1 - distance
                document = similar_results['documents'][0][i]
                
                # 应用相似度阈值
                if similarity < threshold:
                    continue
                
                search_results.append({
                    'email_id': result_email_id,
                    'similarity': round(similarity, 4),
                    'distance': round(distance, 4),
                    'content_preview': document[:200] + '...' if len(document) > 200 else document,
                    'label': label
                })
        
        # --- 3.3 空结果处理 ---
        if len(search_results) == 0:
            logger.info("无符合条件的相似邮件")
            search_results.append({
                'email_id': email_id if email_id else '',
                'similarity': 0.0,
                'distance': 0.0,
                'content_preview': '未找到符合相似度阈值的相似邮件',
                'label': '未知'
            })
        
        # --- 4. 返回统计信息 + 检索结果 ---
        return jsonify({
            'code': 200,
            'success': True,
            'message': '向量检索成功',
            'data': {
                'stats': stats,
                'results': search_results
            }
        })
        
    except Exception as e:
        logger.error(f"向量数据查询失败: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,
            'success': False,
            'message': f'服务器内部错误：{str(e)}',
            'error': str(e)
        }), 500