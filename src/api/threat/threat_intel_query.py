"""
威胁情报查询接口 - VirusTotal 高并发重构版
路径: src/api/threat_query.py
"""

from flask import Blueprint, request, jsonify
import requests
import os
import base64
import pymysql
from src.utils.logger import logger
from data.db_init import get_db_connection  # ✅ 接入统一连接池

threat_query_bp = Blueprint('threat_query', __name__)

# 配置从环境变量获取
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY")
BASE_URL = "https://www.virustotal.com/api/v3"

headers = {
    "accept": "application/json",
    "x-apikey": VIRUSTOTAL_API_KEY
}

# ==================== VT 查询工具函数 ====================

def query_ip(ip):
    url = f"{BASE_URL}/ip_addresses/{ip}"
    resp = requests.get(url, headers=headers, timeout=10) # ✅ 严格超时
    resp.raise_for_status()
    return resp.json()

def query_url(url_str):
    encoded_url = base64.urlsafe_b64encode(url_str.encode()).decode().strip("=")
    url = f"{BASE_URL}/urls/{encoded_url}"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    result['original_url'] = url_str
    return result

def query_file(file_hash):
    url = f"{BASE_URL}/files/{file_hash}"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

def query_domain(domain):
    try:
        url = f"{BASE_URL}/domains/{domain}"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return query_url(domain) # 回退 URL 查询
        raise e

# ==================== 核心 API 接口 ====================

@threat_query_bp.route('/threat_query', methods=['POST'])
def query_threat():
    """
    批量查询威胁情报
    """
    try:
        data = request.get_json() or {}
        ips = data.get('ips', [])
        domains = data.get('domains', [])
        hashes = data.get('hashes', [])

        if not any([ips, domains, hashes]):
            return jsonify({"status": "error", "message": "缺少查询参数"}), 200

        results = {"ips": {}, "domains": {}, "hashes": {}}

        # 1. 批量查询逻辑 (此处逻辑保持，增加了异常捕获)
        for ip in ips:
            try: results["ips"][ip] = query_ip(ip)
            except Exception as e: results["ips"][ip] = {"error": str(e)}

        for domain in domains:
            try: results["domains"][domain] = query_domain(domain)
            except Exception as e: results["domains"][domain] = {"error": str(e)}

        for file_hash in hashes:
            try: results["hashes"][file_hash] = query_file(file_hash)
            except Exception as e: results["hashes"][file_hash] = {"error": str(e)}

        return jsonify({
            "status": "success",
            "results": results
        }), 200

    except Exception as e:
        logger.error(f"💥 威胁情报接口异常: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 200


@threat_query_bp.route('/update_threat_results', methods=['POST'])
def update_threat_results():
    """
    将 VT 查询到的风险结果更新到数据库 - 适配 500 并发连接池
    """
    try:
        data = request.get_json() or {}
        email_id = data.get("email_id")
        # 假设这里传过来的是计算好的风险分数或结果字符串
        vt_url_res = data.get("vt_url_result")
        vt_ip_res = data.get("vt_ip_result")
        vt_file_res = data.get("vt_file_result")

        if not email_id:
            return jsonify({"success": False, "message": "缺少 email_id"}), 200

        # ✅ 获取数据库连接
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # 💡 使用原子性更新：如果 VT 结果显示风险，更新 final_decision
                # 这里假设 vt_xxx_result 是数字 (0安全, 1可疑, 2风险)
                sql = """
                    UPDATE email_data 
                    SET vt_url_result = %s, 
                        vt_ip_result = %s, 
                        vt_file_result = %s,
                        final_decision = GREATEST(final_decision, %s, %s, %s)
                    WHERE email_id = %s
                """
                # GREATEST 函数可以确保 final_decision 始终保留所有检测模块中最高的那一个风险等级
                params = [
                    vt_url_res, vt_ip_res, vt_file_res, 
                    vt_url_res or 0, vt_ip_res or 0, vt_file_res or 0,
                    email_id
                ]
                cursor.execute(sql, params)
                
                if cursor.rowcount == 0:
                    return jsonify({"success": False, "message": "未找到邮件记录"}), 200

                return jsonify({"success": True, "message": "威胁情报同步成功"}), 200
        except Exception as db_e:
            logger.error(f"❌ 数据库更新威胁情报失败: {db_e}", exc_info=True)
            return jsonify({"success": False, "message": "数据库操作失败"}), 200
        finally:
            conn.close() # ✅ 必须归还连接池

    except Exception as e:
        logger.error(f"💥 威胁情报同步接口异常: {e}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 200