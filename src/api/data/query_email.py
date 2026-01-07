# /src/api/email_query.py
from flask import Blueprint, request, jsonify
from dotenv import load_dotenv
import pymysql
import os
from pymysql.cursors import DictCursor
from data.db_init import get_db_connection

# 加载环境变量
load_dotenv()

# 初始化Flask蓝图
query_email_bp = Blueprint('query_email', __name__)

@query_email_bp.route('/email_query', methods=['GET'])
def email_query():
    """
    邮件查询接口（GET）
    功能：根据email_id查询邮件完整信息，支持其他可选参数过滤
    请求参数：
      - email_id：邮件唯一ID（必传）
      - 其他可选参数：如sender/recipient等（可选，用于额外过滤）
    返回格式：JSON，直接返回数据库查询的字典结果
    """
    # 1. 核心参数校验
    email_id = request.args.get('email_id')
    if not email_id:
        return jsonify({
            "code": 400,
            "message": "请求参数缺失：缺少必传参数email_id",
            "data": None
        }), 400
    
    # 2. 构建查询条件（基础条件+可选参数）
    query_conditions = [("email_id", email_id)]
    # 提取其他可选参数（如需扩展过滤条件，可在此添加）
    optional_params = ['sender', 'recipient', 'label', 'phishing_type']
    for param in optional_params:
        param_value = request.args.get(param)
        if param_value:
            query_conditions.append((param, param_value))
    
    # 3. 数据库查询
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(DictCursor) as cursor:
            # 构建SQL语句
            where_clause = " AND ".join([f"{k} = %s" for k, _ in query_conditions])
            sql = f"""
                SELECT * FROM email_data 
                WHERE {where_clause}
                LIMIT 1
            """
            # 提取查询参数值
            query_values = [v for _, v in query_conditions]
            
            cursor.execute(sql, query_values)
            email_data = cursor.fetchone()  # 直接返回字典格式结果
            
            # 4. 结果返回
            if email_data:
                return jsonify({
                    "code": 200,
                    "message": "邮件查询成功",
                    "data": email_data  # 原生字典，无额外格式化
                }), 200
            else:
                return jsonify({
                    "code": 404,
                    "message": f"未找到匹配条件的邮件（email_id: {email_id}）",
                    "data": None
                }), 404
    
    # 数据库异常处理
    except pymysql.MySQLError as e:
        error_msg = f"数据库查询失败：{str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "message": error_msg,
            "data": None
        }), 500
    # 通用异常处理
    except Exception as e:
        error_msg = f"接口执行异常：{str(e)}"
        print(error_msg)
        return jsonify({
            "code": 500,
            "message": error_msg,
            "data": None
        }), 500
    # 确保数据库连接关闭
    finally:
        if conn:
            conn.close()
