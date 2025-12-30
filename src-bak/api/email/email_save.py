import json
import uuid
import pymysql
from datetime import datetime
from flask import Blueprint, request, jsonify
from src.utils.logger import logger
from data.db_init import get_db_connection  # 确保这里是池化连接

save_email_bp = Blueprint('save_email', __name__)

# email_data 表的全部字段
TABLE_FIELDS = [
    "email_id", "sender", "recipient", "subject", "send_time",
    "content_text", "client_ip", "from_domain", "header_list",
    "url_list", "attachment_list",
    "vt_url_result", "vt_ip_result", "vt_file_result",
    "sandbox_result", "ai_result", "ai_reason",  # 补全 ai_reason
    "manual_review", "manual_result",
    "final_decision", "is_alert", "is_block",    # 补全新增字段
    "label", "phishing_type", "data_version"
]

DEFAULT_DATA_VERSION = 1

# ====================== 优化后的 DB 写入函数 ======================
def insert_email_to_db(data: dict):
    conn = None
    try:
        conn = get_db_connection()
        # 使用 with 语句确保 cursor 自动关闭
        with conn.cursor() as cursor:
            fields = []
            values = []
            placeholders = []

            for f in TABLE_FIELDS:
                if data.get(f) is not None:
                    fields.append(f"`{f}`")  # 增加反引号防止关键词冲突
                    values.append(data[f])
                    placeholders.append("%s")

            if not fields:
                logger.warning("插入数据库失败：无有效字段")
                return False

            sql = f"INSERT INTO email_data ({', '.join(fields)}) VALUES ({', '.join(placeholders)})"
            cursor.execute(sql, values)
            # 不需要手动 commit，因为 get_db_connection 设置了 autocommit=True
            # 如果没设，则需要 conn.commit()
            logger.info(f"数据库插入成功: email_id={data.get('email_id')}")
            return True
    except Exception as e:
        logger.error(f"❌ 数据库写入失败: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()  # ✅ 必须归还连接池

# ========================== API 接口 ==========================
@save_email_bp.route("/save_email", methods=["POST"])
def save_email():
    try:
        req = request.get_json() or {}
        email_id = req.get("email_id") or str(uuid.uuid4())

        # 构造数据对象
        data = {field: req.get(field) for field in TABLE_FIELDS}
        data["email_id"] = email_id

        # 时间格式处理（修复兼容问题）
        send_time = data.get("send_time")
        if send_time:
            if isinstance(send_time, str):
                # 兼容常见时间格式（空格/ T 分隔）
                send_time = send_time.replace(' ', 'T')
                try:
                    data["send_time"] = datetime.fromisoformat(send_time.replace('Z', '+00:00'))
                except:
                    # 兜底：直接存储字符串格式
                    data["send_time"] = req.get("send_time")
            elif isinstance(send_time, datetime):
                data["send_time"] = send_time
        else:
            # 绝对兜底：避免空值
            data["send_time"] = datetime.now()

        if data["data_version"] is None:
            data["data_version"] = DEFAULT_DATA_VERSION

        # 写入数据库
        if insert_email_to_db(data):
            return jsonify({
                "success": True, 
                "email_id": email_id,
                "message": "邮件数据保存成功"
            }), 200
        else:
            return jsonify({
                "success": False, 
                "message": "数据库写入失败"
            }), 500

    except Exception as e:
        logger.error(f"💥 保存邮件异常: {e}", exc_info=True)
        return jsonify({
            "success": False, 
            "message": f"保存失败: {str(e)}"
        }), 500


@save_email_bp.route("/update_email_risk", methods=["POST"])
def update_email_risk():
    """
    通过 email_id 更新风险相关字段 + 邮件内容字段，适配高并发连接池
    """
    try:
        req = request.get_json() or {}
        email_id = req.get("email_id")
        
        # 参数校验（规范HTTP返回码）
        if not email_id:
            return jsonify({
                "success": False, 
                "message": "缺少email_id参数"
            }), 400

        # 扩展白名单：加入邮件内容相关字段
        risk_fields = [
            # 风险相关字段（原有）
            "vt_url_result", "vt_ip_result", "vt_file_result", 
            "sandbox_result", "ai_result", "ai_reason", 
            "final_decision", "manual_review", "manual_result",
            "is_alert", "is_block", "label", "phishing_type",
            # 邮件内容字段（新增）
            "sender", "subject", "content_text", "from_domain",
            "url_list", "attachment_list", "header_list", "send_time"
        ]
        
        # 构建更新数据（处理特殊字符）
        update_data = {}
        for k, v in req.items():
            if k in risk_fields:
                # 对字符串字段进行转义处理，防止SQL注入/编码错误
                if isinstance(v, str):
                    update_data[k] = v.replace("'", "''").replace('"', '\\"')
                else:
                    update_data[k] = v
        
        if not update_data:
            return jsonify({
                "success": False, 
                "message": "无有效更新字段"
            }), 400

        # 处理时间格式
        if "send_time" in update_data:
            send_time_val = update_data["send_time"]
            if isinstance(send_time_val, str):
                send_time_val = send_time_val.replace(' ', 'T')
                try:
                    update_data["send_time"] = datetime.fromisoformat(send_time_val.replace('Z', '+00:00'))
                except:
                    # 兜底：保持字符串格式
                    pass

        # 数据库更新操作
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                # 动态构建 SET 子句
                set_clause = ", ".join([f"`{k}`=%s" for k in update_data.keys()])
                sql = f"UPDATE email_data SET {set_clause} WHERE email_id = %s"
                params = list(update_data.values()) + [email_id]
                
                # 关键：打印执行的SQL和参数（排查更新失败原因）
                # logger.info(f"执行更新SQL: {sql}")
                # logger.info(f"更新参数: {params}")
                
                affected_rows = cursor.execute(sql, params)
                
                # 关键：打印影响行数和实际查询结果
                # logger.info(f"更新影响行数: {affected_rows}")
                # 验证email_id是否真的存在
                cursor.execute("SELECT * FROM email_data WHERE email_id = %s", (email_id,))
                db_record = cursor.fetchone()
                if db_record:
                    logger.info(f"数据库中存在该记录: email_id={email_id}")
                else:
                    logger.error(f"数据库中不存在该记录: email_id={email_id}")
                
                if affected_rows == 0:
                    logger.warning(f"更新失败：未找到email_id={email_id}的记录")
                    return jsonify({
                        "success": False, 
                        "message": f"未找到指定email_id的记录（实际执行SQL: {sql}，参数: {params}）"
                    }), 404
                
                logger.info(f"数据库更新成功: email_id={email_id}, 影响行数={affected_rows}")
                return jsonify({
                    "success": True, 
                    "message": "更新成功",
                    "affected_rows": affected_rows
                }), 200
        except Exception as e:
            logger.error(f"❌ 更新风险字段失败: {e}", exc_info=True)
            return jsonify({
                "success": False, 
                "message": f"数据库更新失败: {str(e)}（SQL: {sql}, 参数: {params}）"
            }), 500
        finally:
            if conn:
                conn.close()  # ✅ 归还连接池
            
    except Exception as e:
        logger.error(f"💥 更新风险接口异常: {e}", exc_info=True)
        return jsonify({
            "success": False, 
            "message": f"接口异常: {str(e)}"
        }), 500