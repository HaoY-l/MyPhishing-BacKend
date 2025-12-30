import os
import sys
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify

# 项目根路径配置
current_file = os.path.abspath(__file__)
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_file))))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入工具模块
from src.utils.logger import logger
from data.db_init import get_db_connection

# 创建蓝图
web_email_data_bp = Blueprint('web_email_data', __name__)

# --- 辅助函数：数据库结果处理 ---

def _fetchone_as_dict(cursor):
    """手动将单条记录转为字典"""
    columns = [col[0] for col in cursor.description]
    row = cursor.fetchone()
    if not row:
        return {}
    # 确保 row 是元组或列表，不是字典
    if isinstance(row, dict):
        return row
    return dict(zip(columns, row))

def _fetchall_as_dict(cursor):
    """手动将所有记录转为字典列表"""
    columns = [col[0] for col in cursor.description]
    rows = cursor.fetchall()
    if not rows:
        return []
    # 如果已经是字典列表，直接返回
    if rows and isinstance(rows[0], dict):
        return rows
    return [dict(zip(columns, row)) for row in rows]

# --- 辅助函数：时间解析 (用于趋势图) ---

def _parse_time_range(time_range_str):
    """解析时间范围参数，默认 30d (因为前端趋势图是固定的)"""
    end_time = datetime.now()
    try:
        if time_range_str.endswith('h'):
            hours = int(time_range_str[:-1])
            start_time = end_time - timedelta(hours=hours)
        elif time_range_str.endswith('d'):
            days = int(time_range_str[:-1])
            start_time = end_time - timedelta(days=days)
        else:
            start_time = end_time - timedelta(days=30)
    except:
        start_time = end_time - timedelta(days=30)
    
    return start_time, end_time

def _get_time_buckets(start_time, end_time):
    """返回用于趋势图的 bucket_size 和 time_format"""
    duration = (end_time - start_time).total_seconds()
    
    if duration <= 3600 * 24 * 3:
        bucket_size = 3600
        time_format = '%m-%d %H:00'
    else: 
        bucket_size = 86400
        time_format = '%Y-%m-%d'

    return bucket_size, time_format

def _fill_missing_trend_data(raw_data, start_time, end_time, bucket_size, time_format, trend_keys):
    """填充缺失的时间桶数据并生成 labels"""
    labels = []
    filled_data = {key: [] for key in trend_keys}
    trend_map = {row['time_bucket']: row for row in raw_data}

    # 计算起始和结束时间桶的秒数
    start_ts_sec = int(start_time.timestamp()) // bucket_size * bucket_size
    end_ts_sec = int(end_time.timestamp())
    
    current_ts_sec = start_ts_sec
    while current_ts_sec <= end_ts_sec:
        time_bucket_id = current_ts_sec // bucket_size
        
        timestamp = datetime.fromtimestamp(current_ts_sec)
        labels.append(timestamp.strftime(time_format))
        
        row = trend_map.get(time_bucket_id, {})
        
        for key in trend_keys:
            filled_data[key].append(int(row.get(key, 0)))
        
        current_ts_sec += bucket_size
        
    return labels, filled_data

# --- 映射常量 ---

STATUS_MAP = {
    'normal': 0,     # 正常邮件
    'suspicious': 1,   # 可疑邮件
    'phishing': 2      # 钓鱼邮件
}

# ==============================================================================
# 统一接口：/api/web/emaildata
# ==============================================================================

@web_email_data_bp.route('/emaildata', methods=['GET'])
def get_all_email_data():
    """
    统一接口：一次性获取仪表板所有统计、趋势、TOP列表和邮件列表数据。
    """
    conn = None
    cursor = None
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # --- 1. 列表查询参数解析 (用于邮件列表) ---
        page = int(request.args.get('page', 1))
        size = int(request.args.get('size', 10))
        status = request.args.get('status')
        keyword = request.args.get('keyword')
        
        if page < 1: page = 1
        if size < 1: size = 10
        offset = (page - 1) * size

        # --- 2. 核心统计数据 ---
        summary_query = """
        SELECT 
            COUNT(*) as total_count,
            COALESCE(SUM(CASE WHEN final_decision = 0 THEN 1 ELSE 0 END), 0) as normal_count,
            COALESCE(SUM(CASE WHEN final_decision = 1 THEN 1 ELSE 0 END), 0) as suspicious_count,
            COALESCE(SUM(CASE WHEN final_decision = 2 THEN 1 ELSE 0 END), 0) as phishing_count
        FROM email_data
        """
        cursor.execute(summary_query)
        summary = _fetchone_as_dict(cursor)
        
        # 添加调试日志
        # logger.info(f"Summary data: {summary}")
        
        # 安全获取数值
        total_count = int(summary.get('total_count') or 0)
        phishing_count = int(summary.get('phishing_count') or 0)
        normal_count = int(summary.get('normal_count') or 0)
        suspicious_count = int(summary.get('suspicious_count') or 0)

        stats = {
            'totalCount': total_count,
            'normalCount': normal_count,
            'phishingCount': phishing_count,
            'suspiciousCount': suspicious_count,
        }
        
        # --- 3. 邮件趋势分析 ---
        time_range = '30d' # 前端固定为近 30 天
        start_time, end_time = _parse_time_range(time_range)
        bucket_size, time_format = _get_time_buckets(start_time, end_time)

        trend_query = """
        SELECT 
            UNIX_TIMESTAMP(created_at) DIV %s as time_bucket,
            COUNT(*) as new_count
        FROM email_data
        WHERE created_at >= %s AND created_at <= %s
        GROUP BY time_bucket
        ORDER BY time_bucket ASC
        """
        cursor.execute(trend_query, (bucket_size, start_time, end_time))
        trend_raw = _fetchall_as_dict(cursor)
        
        labels, filled = _fill_missing_trend_data(
            trend_raw, start_time, end_time, bucket_size, time_format, 
            ['new_count']
        )
        
        total_data = []
        cumulative_sum = 0
        for new_count in filled['new_count']:
            cumulative_sum += new_count
            total_data.append(cumulative_sum)

        trend = {
            'labels': labels,
            'totalData': total_data,
            'newData': filled['new_count']
        }
        
        # --- 4. TOP 风险发件人 ---
        top_senders_query = """
        SELECT sender, COUNT(*) as count
        FROM email_data
        WHERE final_decision = 2
        GROUP BY sender
        ORDER BY count DESC
        LIMIT 5
        """
        cursor.execute(top_senders_query)
        top_senders_raw = _fetchall_as_dict(cursor)
        
        top_risk_senders = []
        phishing_count_safe = phishing_count if phishing_count > 0 else 1
        
        for row in top_senders_raw:
            sender = row['sender']
            domain = sender.split('@')[-1] if '@' in sender else '未知'
            rate = round((row['count'] / phishing_count_safe) * 100, 1)
            
            top_risk_senders.append({
                'sender': sender,
                'domain': domain,
                'count': int(row['count']),
                'rate': f"{rate}"
            })
        
        # --- 5. TOP 风险收件人 ---
        top_recipients_query = """
        SELECT recipient, COUNT(*) as count
        FROM email_data
        WHERE final_decision = 2
        GROUP BY recipient
        ORDER BY count DESC
        LIMIT 5
        """
        cursor.execute(top_recipients_query)
        top_recipients_raw = _fetchall_as_dict(cursor)
        
        top_risk_recipients = [
            {'recipient': row['recipient'], 'count': int(row['count'])}
            for row in top_recipients_raw
        ]
        
        # --- 6. 邮件记录列表 ---
        where_clauses = ["1=1"]
        list_params = []
        
        if status in STATUS_MAP:
            where_clauses.append("final_decision = %s")
            list_params.append(STATUS_MAP[status])
        
        if keyword:
            where_clauses.append("(sender LIKE %s OR subject LIKE %s)")
            list_params.append(f"%{keyword}%")
            list_params.append(f"%{keyword}%")

        where_sql = " AND ".join(where_clauses)
        
        # 获取总记录数和总页数
        count_query = f"""
        SELECT COUNT(*) as total_records FROM email_data WHERE {where_sql}
        """
        cursor.execute(count_query, tuple(list_params))
        count_result = _fetchone_as_dict(cursor)
        total_records = int(count_result.get('total_records') or 0)
        total_pages = (total_records + size - 1) // size if total_records > 0 else 0
        
        # 获取当前页的邮件记录
        list_query = f"""
        SELECT 
            email_id, sender, recipient, subject, created_at, final_decision
        FROM email_data
        WHERE {where_sql}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """
        list_params.extend([size, offset])
        cursor.execute(list_query, tuple(list_params))
        records_raw = _fetchall_as_dict(cursor)

        # 格式化列表数据
        email_list = []
        decision_map = {0: 'normal', 1: 'suspicious', 2: 'phishing'}
        
        for row in records_raw:
            created_at = row.get('created_at')
            time_str = created_at.strftime('%Y-%m-%d %H:%M:%S') if isinstance(created_at, datetime) else str(created_at)

            email_list.append({
                'id': row.get('email_id', ''),
                'sender': row.get('sender') or '未知',
                'recipient': row.get('recipient') or '未知',
                'subject': row.get('subject') or '无主题',
                'time': time_str,
                'status': decision_map.get(row.get('final_decision'), 'suspicious'),
            })

        # --- 7. 统一返回最终结果（字段名与前端一致）---
        return jsonify({
            'code': 200,
            'success': True,
            'message': '所有邮件数据查询成功',
            'data': {
                'stats': stats,                          # 改名：totalStats -> stats
                'trend': trend,                          # 改名：trendData -> trend
                'topRiskSenders': top_risk_senders,
                'topRiskRecipients': top_risk_recipients,
                'emails': {                              # 改名：emailList -> emails
                    'list': email_list,
                    'totalPages': total_pages,
                    'totalRecords': total_records
                }
            }
        })
        
    except Exception as e:
        logger.error(f"Unified All Data API error: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,
            'success': False,
            'message': f'服务器内部错误：{str(e)}',
            'error': str(e)
        }), 500
    
    finally:
        if cursor: cursor.close()
        if conn: conn.close()