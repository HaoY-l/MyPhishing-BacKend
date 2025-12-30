"""
查询Chroma向量数据库API
路径: src/api/data/query_chroma_api.py
接口: 
  - GET /api/data/query_chroma?limit=10
  - POST /api/data/search_chroma
"""

import chromadb
import os
import sys
from flask import Blueprint, request, jsonify

# 添加项目根目录到Python路径
current_file = os.path.abspath(__file__)
data_dir = os.path.dirname(current_file)  # src/api/data
api_dir = os.path.dirname(data_dir)  # src/api
src_dir = os.path.dirname(api_dir)  # src
project_root = os.path.dirname(src_dir)  # 项目根目录

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.logger import logger

# 创建蓝图
query_chroma_bp = Blueprint('query_chroma', __name__)

@query_chroma_bp.route('/query_chroma', methods=['GET'])
def query_chroma():
    """
    查询Chroma数据库统计信息
    参数: limit (可选，默认10)
    示例: GET /api/data/query_chroma?limit=20
    """
    try:
        # 获取参数，默认10条
        limit = request.args.get('limit', 10000000, type=int)
        
        # 初始化 Chroma 客户端
        client = chromadb.PersistentClient(path="./chroma_db")
        
        # 获取集合
        collection = client.get_or_create_collection(
            name="email_knowledge_base",
            metadata={"hnsw:space": "cosine"}
        )
        
        # 获取集合统计信息
        count = collection.count()
        
        # 获取指定数量的数据
        results = collection.get(
            limit=limit,
            include=["metadatas", "documents"]
        )
        
        return jsonify({
            'success': True,
            'total_count': count,
            'limit': limit,
            'returned_count': len(results['ids']),
            'data': {
                'ids': results['ids'],
                'metadatas': results['metadatas'],
                'documents': [doc[:200] + '...' if len(doc) > 200 else doc for doc in results['documents']]  # 截断长文本
            }
        }), 200
    
    except Exception as e:
        logger.error(f"❌ 查询 Chroma 失败：{str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'查询失败: {str(e)}'
        }), 500


@query_chroma_bp.route('/search_chroma', methods=['POST'])
def search_chroma():
    """
    向量相似度搜索API
    
    请求体: 
    {
        "query": "搜索的邮件内容",
        "top_k": 5  // 可选，返回前N个最相似的结果，默认5
    }
    
    功能说明：
    - 输入一段文本（邮件内容、主题等）
    - 系统会将文本转换为向量
    - 在数据库中查找最相似的邮件
    - 返回相似度最高的top_k个结果
    
    使用场景：
    1. 检测钓鱼邮件：输入可疑邮件内容，查找相似的已知钓鱼邮件
    2. 邮件分类：根据内容找到相似邮件的类别
    3. 重复检测：检查是否有相似的邮件已经存在
    """
    try:
        from sentence_transformers import SentenceTransformer
        
        # 获取请求参数
        data = request.get_json()
        query_text = data.get('query', '')
        top_k = data.get('top_k', 5)
        
        if not query_text:
            return jsonify({
                'success': False,
                'message': '查询内容不能为空'
            }), 400
        
        logger.info(f"搜索查询: {query_text[:100]}...")
        
        # 加载模型
        local_model_path = os.path.join(project_root, "data", "bge-small")
        model = SentenceTransformer(local_model_path)
        
        # 生成查询向量
        query_embedding = model.encode(query_text).tolist()
        
        # 初始化 Chroma
        client = chromadb.PersistentClient(path="./chroma_db")
        collection = client.get_or_create_collection(
            name="email_knowledge_base",
            metadata={"hnsw:space": "cosine"}
        )
        
        # 向量搜索（余弦相似度）
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["metadatas", "documents", "distances"]
        )
        
        # 格式化结果
        search_results = []
        for i in range(len(results['ids'][0])):
            search_results.append({
                'id': results['ids'][0][i],
                'email_id': results['metadatas'][0][i]['email_id'],
                'label': results['metadatas'][0][i]['label'],
                'distance': results['distances'][0][i],  # 距离越小越相似
                'similarity': 1 - results['distances'][0][i],  # 相似度 (0-1)
                'document': results['documents'][0][i][:500] + '...' if len(results['documents'][0][i]) > 500 else results['documents'][0][i]
            })
        
        return jsonify({
            'success': True,
            'query': query_text,
            'top_k': top_k,
            'results': search_results
        }), 200
    
    except Exception as e:
        logger.error(f"❌ 搜索失败：{str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'搜索失败: {str(e)}'
        }), 500