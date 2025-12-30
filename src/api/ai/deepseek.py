"""
AI钓鱼邮件分析接口 - DeepSeek集成版
路径: src/api/ai_chat.py
接口: POST /api/ai/aichat
功能: 邮件查询 -> 向量化 -> 相似检索 -> AI分析 -> 结构化结果
"""

from flask import Blueprint, request, jsonify
from dotenv import load_dotenv
import requests,pymysql
import os
import sys
import json
from datetime import datetime
from src.utils.models_loader import ModelManager
from src.utils.logger import logger
from data.db_init import get_db_connection

# 加载环境变量
load_dotenv()

# ==================== 初始化蓝图 ====================
ai_bp = Blueprint('ai_chat', __name__)

# ==================== 核心工具函数 ====================

def get_email_by_id(email_id):
    conn = get_db_connection() # 现在从池里拿
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor: 
            cursor.execute("SELECT * FROM email_data WHERE email_id = %s", (email_id,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"❌ 查询邮件失败: {str(e)}")
        return None
    finally:
        conn.close() # 💥 极其重要：归还连接池，否则池子很快会满


def vectorize_email(email_data):
    """
    将邮件信息向量化
    返回: (向量列表, 拼接的文本)
    """
    model = ModelManager.get_embedding_model()
    
    # 拼接核心字段
    text_parts = []
    
    if email_data.get('subject'):
        text_parts.append(f"Subject: {email_data['subject']}")
    
    if email_data.get('sender'):
        text_parts.append(f"From: {email_data['sender']}")
    
    if email_data.get('from_domain'):
        text_parts.append(f"Domain: {email_data['from_domain']}")
    
    if email_data.get('content_text'):
        text_parts.append(f"Content: {email_data['content_text'][:500]}")  # 限制长度
    
    if email_data.get('url_list'):
        try:
            urls = json.loads(email_data['url_list']) if isinstance(email_data['url_list'], str) else []
            if urls:
                text_parts.append(f"URLs: {' '.join(urls[:5])}")  # 只取前5个URL
        except:
            pass
    
    document_text = "\n".join(text_parts)
    
    # 生成向量
    embedding = model.encode(document_text).tolist()
    logger.info(f"✅ 邮件向量化成功，维度: {len(embedding)}")
    
    return embedding, document_text


def search_similar_emails(email_embedding, top_k=5):
    """
    在Chroma中检索相似邮件
    返回: list (相似邮件信息列表)
    """
    try:
        # 动态获取 collection
        client = ModelManager.get_chroma_client()
        collection = client.get_or_create_collection("email_knowledge_base")
        
        results = collection.query(
            query_embeddings=[email_embedding],
            n_results=top_k
        )
        
        similar_emails = []
        
        if results.get('ids') and len(results['ids']) > 0 and len(results['ids'][0]) > 0:
            for idx, email_id in enumerate(results['ids'][0]):
                distance = results['distances'][0][idx] if results.get('distances') else 0
                similarity = 1 - distance  # 转换为相似度
                
                email_info = get_email_by_id(email_id)
                if email_info:
                    email_info['similarity'] = round(similarity, 4)
                    similar_emails.append(email_info)
        
        logger.info(f"✅ 检索到 {len(similar_emails)} 封相似邮件")
        return similar_emails
        
    except Exception as e:
        logger.error(f"❌ 相似邮件检索失败: {str(e)}", exc_info=True)
        return []


def save_ai_analysis_to_db(email_id, ai_result):
    """
    保存AI结果（ai_result/ai_reason），并同步将final_decision设为与ai_result相同值
    """
    conn = None
    try:
        conn = get_db_connection(use_db=True)
        cursor = conn.cursor(pymysql.cursors.DictCursor)  
        
        # 提取AI核心字段（ai_result + ai_reason）
        ai_result_code = ai_result.get("result", 0)  # AI结果：0=安全/1=可疑/2=风险
        ai_reason = ai_result.get("reason", "未获取到分析理由")
        
        # 关键修改：新增 final_decision = %s，与ai_result_code值一致
        cursor.execute("""
            UPDATE email_data 
            SET 
                ai_result = %s,        -- AI结果
                ai_reason = %s,        -- AI分析理由
                final_decision = %s    -- 系统最终决策：同步AI结果
            WHERE email_id = %s
        """, (
            ai_result_code,  # 对应ai_result
            ai_reason,       # 对应ai_reason
            ai_result_code,  # 对应final_decision（与AI结果相同）
            email_id         # 目标邮件ID
        ))
        
        conn.commit()
        logger.info(f"✅ AI结果+最终决策已同步存入数据库: email_id={email_id}, final_decision={ai_result_code}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 保存AI结果+最终决策失败: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


def chat_with_deepseek(prompt, api_key, api_endpoint, model_name):
    """
    调用DeepSeek API进行邮件分析
    返回: (结果dict, 状态码)
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": """你是专业的钓鱼邮件检测分析师。请严格按以下规则分析邮件：

分析步骤：
1. 检查邮件源信息（发件人、域名、IP、文件MD5等），风险信息如vt_url_result、vt_ip_result、vt_file_result、sandbox_result等
2. 分析邮件内容特征（语言、紧急性、请求等）
3. 根据现有的邮件特征、内容特征、邮件源信息，对比相似邮件的特征，分析是否存在异常
4. 综合判断邮件是否为钓鱼邮件，返回结果为JSON格式

输出格式（必须是JSON）：
{
    "result": 0,  // 0=安全 / 1=可疑 / 2=风险
    "reason": "详细分析理由，至少100字",
    "phishing_type": "钓鱼类型（具体类型或'无'）",
    "confidence": 0.95  // 置信度0-1
}

禁止返回其他格式或无关内容。"""
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 1000
    }
    
    try:
        logger.info(f"正在调用DeepSeek API: {api_endpoint}")
        response = requests.post(api_endpoint, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        resp_data = response.json()
        
        # 提取AI回复
        if "choices" in resp_data and len(resp_data["choices"]) > 0:
            ai_content = resp_data["choices"][0]["message"]["content"].strip()
            logger.info(f"✅ DeepSeek返回结果")
            
            # 尝试解析JSON
            try:
                result_json = json.loads(ai_content)
                return result_json, 200
            except json.JSONDecodeError:
                logger.error(f"⚠️ AI返回非JSON格式: {ai_content[:2000]}")
                # 尝试提取JSON
                import re
                json_match = re.search(r'\{.*\}', ai_content, re.DOTALL)
                if json_match:
                    try:
                        result_json = json.loads(json_match.group())
                        return result_json, 200
                    except:
                        pass
                
                return {
                    "error": "AI返回非标准JSON格式",
                    "raw_content": ai_content[:5000]
                }, 500
        else:
            logger.error("❌ AI返回空内容")
            return {"error": "AI返回空内容"}, 5000
            
    except requests.exceptions.Timeout:
        logger.error("❌ DeepSeek API请求超时")
        return {"error": "请求超时"}, 504
    except requests.exceptions.HTTPError as e:
        logger.error(f"❌ HTTP错误: {e.response.status_code}")
        return {"error": f"HTTP {e.response.status_code}"}, e.response.status_code
    except Exception as e:
        logger.error(f"❌ DeepSeek调用失败: {str(e)}", exc_info=True)
        return {"error": str(e)}, 500


# ==================== API 接口 ====================

@ai_bp.route('/aichat', methods=['POST'])
def aichat():
    """
    AI钓鱼邮件分析接口
    
    请求参数 (JSON):
    {
        "email_id": "邮件ID（必传）"
    }
    
    环境变量配置 (.env):
    DEEPSEEK_API_KEY=your-api-key
    DEEPSEEK_API_ENDPOINT=https://api.deepseek.com/chat/completions
    DEEPSEEK_MODEL_NAME=deepseek-chat
    
    返回格式:
    {
        "code": 200,
        "message": "成功",
        "data": {
            "original_email": {...},
            "similar_emails": [...],
            "ai_analysis": {
                "result": 0,
                "reason": "...",
                "phishing_type": "...",
                "confidence": 0.95
            }
        }
    }
    """
    
    try:
        # ===== 1. 从环境变量读取DeepSeek配置 =====
        api_key = os.getenv('DEEPSEEK_API_KEY', '').strip()
        api_endpoint = os.getenv('DEEPSEEK_API_ENDPOINT', 'https://api.deepseek.com/chat/completions').strip()
        model_name = os.getenv('DEEPSEEK_MODEL_NAME', 'deepseek-chat').strip()
        
        if not api_key:
            logger.error("❌ 缺少环境变量: DEEPSEEK_API_KEY")
            return jsonify({
                "code": 500,
                "message": "服务配置错误: 缺少DEEPSEEK_API_KEY",
                "data": None
            }), 500
        
        # ===== 2. 参数校验 =====
        req_data = request.get_json() or {}
        email_id = req_data.get('email_id', '').strip()
        
        if not email_id:
            return jsonify({
                "code": 400,
                "message": "缺少必传参数: email_id",
                "data": None
            }), 400
        
        logger.info(f"开始分析邮件: {email_id}")
        
        # ===== 2. 查询原始邮件 =====
        email_data = get_email_by_id(email_id)
        if not email_data:
            return jsonify({
                "code": 404,
                "message": f"未找到email_id为 [{email_id}] 的邮件",
                "data": None
            }), 404
        
        # ===== 3. 向量化邮件 =====
        try:
            email_embedding, document_text = vectorize_email(email_data)
        except Exception as e:
            logger.error(f"向量化失败: {str(e)}")
            return jsonify({
                "code": 500,
                "message": f"邮件向量化失败: {str(e)}",
                "data": None
            }), 500
        
        # ===== 4. 检索相似邮件 =====
        similar_emails = search_similar_emails(email_embedding, top_k=5)
        
        # ===== 5. 构造AI提示词 =====
        similar_emails_json = json.dumps(
            similar_emails,
            ensure_ascii=False,
            default=str,
            indent=2
        )
        
        email_data_json = json.dumps(
            email_data,
            ensure_ascii=False,
            default=str,
            indent=2
        )
        
        prompt = f"""请分析以下邮件是否为钓鱼邮件：

【待分析邮件信息】
{email_data_json}

【相似邮件参考（Top5）】
{similar_emails_json}

请根据邮件源信息、内容特征、以及相似邮件特征进行综合分析，返回JSON格式结果。"""
        
        # ===== 6. 调用DeepSeek =====
        ai_result, status_code = chat_with_deepseek(
            prompt,
            api_key,
            api_endpoint,
            model_name
        )
        
        if status_code != 200:
            return jsonify({
                "code": status_code,
                "message": "AI分析失败",
                "data": ai_result
            }), status_code
        save_success = save_ai_analysis_to_db(email_id, ai_result)
        if not save_success:
            logger.warning(f"⚠️ AI分析结果保存失败，但不影响接口返回: email_id={email_id}")
        
        # ===== 7. 返回完整结果 =====
        return jsonify({
            "code": 200,
            "message": "AI分析完成",
            "data": {
                "original_email": email_data,
                "similar_emails": similar_emails,
                "ai_analysis": ai_result
            }
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 接口异常: {str(e)}", exc_info=True)
        return jsonify({
            "code": 500,
            "message": f"服务异常: {str(e)}",
            "data": None
        }), 500
