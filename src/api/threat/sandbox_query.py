"""
沙箱查询接口 - 高并发重构版
路径: src/api/sandbox_query.py
"""

from flask import Blueprint, request, jsonify
import requests
import os
import pymysql
from src.utils.logger import logger
from typing import Dict, Any, Optional, List
from data.db_init import get_db_connection  # ✅ 修正：使用统一的数据库连接池

# 初始化蓝图
sandbox_query_bp = Blueprint('sandbox_query', __name__)

# 配置从环境变量读取
THREATBOOK_API_KEY = os.getenv("THREATBOOK_API_KEY")
THREATBOOK_BASE_URL = "https://api.threatbook.cn/v3"
DEFAULT_SANDBOX_TYPE = os.getenv("DEFAULT_SANDBOX_TYPE", "win7_sp1_enx86_office2013")

# 全局请求头
headers = {"Accept": "application/json"}

# 风险等级映射
RISK_MAPPING = {
    "clean": 0,
    "suspicious": 1,
    "malicious": 2,
    "unknown": None
}

THREATBOOK_ERRORS = {
    400: "请求参数错误",
    401: "API密钥错误",
    429: "请求频率超限",
    500: "微步内部错误"
}

# ==================== 工具函数 (保持逻辑，优化稳定性) ====================

def get_risk_level_from_report(report: Dict[str, Any], target_type: str) -> Optional[int]:
    """从微步报告提取风险等级"""
    if "error" in report or report.get("response_code") != 0:
        return None
    
    data = report.get("data", {})
    try:
        if target_type == "file":
            risk = data.get("summary", {}).get("threat_level", "unknown")
        elif target_type == "domain":
            risk = data.get("threat_level", "unknown")
        elif target_type == "ip":
            # IP信誉逻辑
            ip_key = list(data.keys())[0] if data else ""
            if ip_key and data[ip_key].get("is_malicious"):
                risk = "malicious" if data[ip_key].get("severity") in ["critical", "high"] else "suspicious"
            else:
                risk = "clean"
        else:
            risk = "unknown"
        return RISK_MAPPING.get(risk.lower(), None)
    except:
        return None

def query_single_resource(resource_type: str, value: str) -> Dict[str, Any]:
    """通用单项查询函数，增强超时控制以支撑并发"""
    endpoint_map = {
        "file": "/file/report",
        "domain": "/url/report",
        "ip": "/scene/ip_reputation"
    }
    url = f"{THREATBOOK_BASE_URL}{endpoint_map[resource_type]}"
    
    # 适配不同接口的参数名
    param_key = "resource" if resource_type != "domain" else "url"
    params = {
        "apikey": THREATBOOK_API_KEY,
        param_key: value,
        "lang": "zh"
    }
    
    try:
        # ✅ 高并发下 timeout 必须严格控制，防止 Worker 被外部接口挂死
        response = requests.get(url, params=params, headers=headers, timeout=10)
        if response.status_code != 200:
            return {"error": THREATBOOK_ERRORS.get(response.status_code, "HTTP Error")}
        return response.json()
    except Exception as e:
        return {"error": str(e)}

# ==================== API 接口 (重构核心逻辑) ====================

@sandbox_query_bp.route('/sandbox_query', methods=['POST'])
def sandbox_analyze():
    """批量沙箱查询接口"""
    try:
        data = request.get_json() or {}
        file_hashes = data.get('file_hashes', [])
        domains = data.get('domains', [])
        ips = data.get('ips', [])

        if not THREATBOOK_API_KEY:
            return jsonify({"status": "error", "error": "API Key missing"}), 500

        results = {"file_reports": {}, "domain_reports": {}, "ip_reports": {}}
        all_risks = []

        # 批量处理
        for h in file_hashes:
            rep = query_single_resource("file", h)
            results["file_reports"][h] = rep
            all_risks.append(get_risk_level_from_report(rep, "file"))

        for d in domains:
            rep = query_single_resource("domain", d)
            results["domain_reports"][d] = rep
            all_risks.append(get_risk_level_from_report(rep, "domain"))

        for i in ips:
            rep = query_single_resource("ip", i)
            results["ip_reports"][i] = rep
            all_risks.append(get_risk_level_from_report(rep, "ip"))

        # 计算最终值
        valid_risks = [r for r in all_risks if r is not None]
        final_res = max(valid_risks) if valid_risks else None

        return jsonify({
            "status": "success",
            "results": results,
            "final_sandbox_result": final_res
        }), 200
    except Exception as e:
        logger.error(f"沙箱分析接口异常: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@sandbox_query_bp.route('/email/update_sandbox_result', methods=['POST'])
def update_sandbox_result():
    """
    更新邮件沙箱结果 - 适配 500 并发连接池
    """
    try:
        data = request.get_json() or {}
        email_id = data.get("email_id")
        sandbox_result = data.get("sandbox_result")

        if not email_id or sandbox_result not in [0, 1, 2]:
            return jsonify({"success": False, "message": "无效参数"}), 200

        # ✅ 从统一连接池获取连接
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                # 💡 并发安全更新逻辑：
                # 1. 更新 sandbox_result
                # 2. final_decision 取当前值和新沙箱结果的较大者，防止结果回退
                sql = """
                    UPDATE email_data 
                    SET sandbox_result = %s,
                        final_decision = IF(final_decision < %s, %s, final_decision)
                    WHERE email_id = %s
                """
                cursor.execute(sql, [sandbox_result, sandbox_result, sandbox_result, email_id])
                
                if cursor.rowcount == 0:
                    return jsonify({"success": False, "message": "邮件记录不存在"}), 200

                return jsonify({"success": True, "email_id": email_id, "result": sandbox_result}), 200
        except Exception as db_e:
            logger.error(f"❌ 数据库更新失败: {db_e}", exc_info=True)
            return jsonify({"success": False, "message": "DB error"}), 200
        finally:
            conn.close()  # ✅ 极其重要：归还连接池
            
    except Exception as e:
        logger.error(f"💥 接口异常: {e}", exc_info=True)
        return jsonify({"success": False, "message": str(e)}), 200