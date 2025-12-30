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
web_dashboard_bp = Blueprint('web_dashboard', __name__)


class DatabaseHelper:
    """数据库辅助类，兼容所有数据库驱动"""
    
    @staticmethod
    def fetchone_as_dict(cursor):
        """将单条记录转为字典"""
        row = cursor.fetchone()
        if not row:
            return None
        
        columns = [col[0] for col in cursor.description]
        
        # 如果已经是字典，直接返回
        if isinstance(row, dict):
            return row
        
        # 如果是元组或列表，转为字典
        if isinstance(row, (tuple, list)):
            return dict(zip(columns, row))
        
        return None
    
    @staticmethod
    def fetchall_as_dict(cursor):
        """将所有记录转为字典列表"""
        rows = cursor.fetchall()
        if not rows:
            return []
        
        columns = [col[0] for col in cursor.description]
        
        result = []
        for row in rows:
            # 如果已经是字典，直接添加
            if isinstance(row, dict):
                result.append(row)
            # 如果是元组或列表，转为字典
            elif isinstance(row, (tuple, list)):
                result.append(dict(zip(columns, row)))
        
        return result


def parse_time_range(time_range_str):
    """解析时间范围参数"""
    end_time = datetime.now()
    
    if time_range_str.endswith('h'):
        hours = int(time_range_str[:-1])
        start_time = end_time - timedelta(hours=hours)
    elif time_range_str.endswith('d'):
        days = int(time_range_str[:-1])
        start_time = end_time - timedelta(days=days)
    else:
        try:
            start_ts, end_ts = time_range_str.split('-')
            start_time = datetime.fromtimestamp(int(start_ts) / 1000)
            end_time = datetime.fromtimestamp(int(end_ts) / 1000)
        except:
            start_time = end_time - timedelta(hours=12)
    
    return start_time, end_time


def get_time_bucket_size(start_time, end_time):
    """根据时间范围自动确定聚合粒度"""
    duration = (end_time - start_time).total_seconds()
    
    if duration <= 3600 * 12:
        return 600, '%H:%M'
    elif duration <= 3600 * 24:
        return 1800, '%H:%M'
    elif duration <= 3600 * 24 * 3:
        return 3600, '%m-%d %H:00'
    elif duration <= 3600 * 24 * 7:
        return 7200, '%m-%d %H:00'
    else:
        return 86400, '%Y-%m-%d'


def _fill_missing_time_buckets(raw_data, start_time, end_time, bucket_size, time_format, trend_keys):
    """
    填充缺失的时间桶数据，确保时间轴完整。
    
    :param raw_data: 数据库查询返回的原始数据列表。
    :param start_time: 查询的起始时间。
    :param end_time: 查询的结束时间。
    :param bucket_size: 时间桶大小（秒）。
    :param time_format: 时间格式化字符串。
    :param trend_keys: 需要填充的趋势数据键名列表。
    :return: 填充后的趋势数据字典。
    """
    
    # 1. 初始化空趋势数据
    filled_data = {'timestamps': []}
    for key in trend_keys:
        filled_data[key] = []

    # 2. 将原始数据转换为以 time_bucket_id 为键的字典
    trend_map = {row['time_bucket']: row for row in raw_data}

    # 3. 计算第一个和最后一个时间桶的秒数，并确保包含最后一个不完整的时间桶
    start_ts_sec = int(start_time.timestamp()) // bucket_size * bucket_size
    
    # 最后一个时间桶的秒数，确保至少包含end_time所在的时间桶
    end_ts_sec = int(end_time.timestamp()) // bucket_size * bucket_size
    if end_time.timestamp() % bucket_size != 0:
        end_ts_sec += bucket_size
    
    # 4. 遍历完整的时间轴并填充数据
    current_ts_sec = start_ts_sec
    while current_ts_sec <= end_ts_sec:
        time_bucket_id = current_ts_sec // bucket_size
        
        # 转换为 datetime 对象进行格式化
        timestamp = datetime.fromtimestamp(current_ts_sec)
        
        # 查找数据或使用 0 填充
        row = trend_map.get(time_bucket_id, {})
        
        filled_data['timestamps'].append(timestamp.strftime(time_format))
        
        for key in trend_keys:
            # 使用 get(key, 0) 确保缺失时为 0
            filled_data[key].append(int(row.get(key, 0)))
        
        # 移动到下一个时间桶
        current_ts_sec += bucket_size
        
    return filled_data


@web_dashboard_bp.route('/dashboard', methods=['GET'])
def get_dashboard_data():
    """获取仪表盘数据"""
    conn = None
    cursor = None
    
    try:
        time_range = request.args.get('timeRange', '12h')
        # 强制使用当前时间来解析时间范围
        start_time, end_time = parse_time_range(time_range) 
        bucket_size, time_format = get_time_bucket_size(start_time, end_time)
        
        logger.info(f"Dashboard query: {time_range}, from {start_time} to {end_time}")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        db_helper = DatabaseHelper()
        
        # ============ 1. 获取汇总数据 ============
        summary_query = """
        SELECT 
            COUNT(*) as total_count,
            COALESCE(SUM(CASE WHEN final_decision = 0 THEN 1 ELSE 0 END), 0) as normal_count,
            COALESCE(SUM(CASE WHEN final_decision = 1 THEN 1 ELSE 0 END), 0) as suspicious_count,
            COALESCE(SUM(CASE WHEN final_decision = 2 THEN 1 ELSE 0 END), 0) as phishing_count,
            COALESCE(SUM(CASE WHEN manual_review = 1 THEN 1 ELSE 0 END), 0) as manual_count,
            COALESCE(SUM(CASE WHEN is_block = 1 THEN 1 ELSE 0 END), 0) as block_count,
            COALESCE(SUM(CASE WHEN is_alert = 1 THEN 1 ELSE 0 END), 0) as alert_count
        FROM email_data
        WHERE created_at >= %s AND created_at <= %s
        """
        cursor.execute(summary_query, (start_time, end_time))
        summary = db_helper.fetchone_as_dict(cursor)
        
        if not summary:
            summary = {
                'total_count': 0, 'normal_count': 0, 'phishing_count': 0,
                'suspicious_count': 0, 'manual_count': 0
            }
        
        # logger.info(f"Summary: {summary}")
        
        # ============ 2. 获取邮件处理趋势数据 (并进行填充) ============
        trend_query = """
        SELECT 
            UNIX_TIMESTAMP(created_at) DIV %s as time_bucket,
            COUNT(*) as total,
            COALESCE(SUM(CASE WHEN final_decision = 0 THEN 1 ELSE 0 END), 0) as normal,
            COALESCE(SUM(CASE WHEN final_decision = 1 THEN 1 ELSE 0 END), 0) as suspicious,
            COALESCE(SUM(CASE WHEN final_decision = 2 THEN 1 ELSE 0 END), 0) as phishing,
            COALESCE(SUM(CASE WHEN manual_review = 1 THEN 1 ELSE 0 END), 0) as manual
        FROM email_data
        WHERE created_at >= %s AND created_at <= %s
        GROUP BY time_bucket
        ORDER BY time_bucket ASC
        """
        cursor.execute(trend_query, (bucket_size, start_time, end_time))
        trend_raw = db_helper.fetchall_as_dict(cursor)
        
        # 使用填充函数
        trend_data = _fill_missing_time_buckets(
            trend_raw, start_time, end_time, bucket_size, time_format, 
            ['total', 'normal', 'phishing', 'suspicious', 'manual']
        )
        
        # ============ 3. 获取拦截与告警趋势 (并进行填充) ============
        action_query = """
        SELECT 
            UNIX_TIMESTAMP(created_at) DIV %s as time_bucket,
            COALESCE(SUM(CASE WHEN is_block = 1 THEN 1 ELSE 0 END), 0) as block_count,
            COALESCE(SUM(CASE WHEN is_alert = 1 THEN 1 ELSE 0 END), 0) as alert_count
        FROM email_data
        WHERE created_at >= %s AND created_at <= %s
        GROUP BY time_bucket
        ORDER BY time_bucket ASC
        """
        cursor.execute(action_query, (bucket_size, start_time, end_time))
        action_raw = db_helper.fetchall_as_dict(cursor)
        
        # 调整键名以匹配前端
        for row in action_raw:
            row['block'] = row.pop('block_count')
            row['alert'] = row.pop('alert_count')

        # 使用填充函数
        action_trend_data = _fill_missing_time_buckets(
            action_raw, start_time, end_time, bucket_size, time_format, 
            ['block', 'alert']
        )
        
        # ============ 4. 获取最近检测记录 (包含 AI 分析内容) ============
        records_query = """
        SELECT 
            email_id, sender,recipient,subject, created_at, final_decision,
            is_block, is_alert, manual_review, ai_reason 
        FROM email_data
        WHERE created_at >= %s AND created_at <= %s
        ORDER BY created_at DESC
        LIMIT 20
        """
        cursor.execute(records_query, (start_time, end_time))
        records_raw = db_helper.fetchall_as_dict(cursor)
        
        records = []
        result_map = {0: '正常邮件', 1: '可疑邮件', 2: '钓鱼邮件'}
        
        for row in records_raw:
            # 确定处理状态
            if row.get('is_block'):
                status = '已拦截'
            elif row.get('is_alert'):
                status = '已告警'
            elif row.get('manual_review'):
                status = '待人工确认'
            else:
                status = '已放行'
            
            # 处理时间格式 - 统一使用 created_at
            created_at = row.get('created_at')
            if created_at:
                if isinstance(created_at, str):
                    time_str = created_at
                elif isinstance(created_at, datetime):
                    time_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    time_str = str(created_at)
            else:
                time_str = '未知'
            
            records.append({
                'id': row.get('email_id', ''),
                'sender': row.get('sender') or '未知',
                'recipient': row.get('recipient') or '未知',
                'subject': row.get('subject') or '无主题',
                'time': time_str,
                'result': result_map.get(row.get('final_decision'), '未知'),
                'status': status,
                # 💥 关键修正：统一字段名以匹配前端 Dashboard.vue
                'ai_reason': row.get('ai_reason') or '无' 
            })
        
        # ============ 5. 返回数据 (核心修改：添加code字段，适配前端拦截器) ============
        return jsonify({
            'code': 200,  # 新增：前端拦截器需要的code字段
            'success': True,
            'message': '仪表盘数据查询成功',  # 新增：前端可捕获的提示信息
            'data': {
                'summary': {
                    'totalCount': int(summary.get('total_count', 0)),
                    'normalCount': int(summary.get('normal_count', 0)),
                    'phishingCount': int(summary.get('phishing_count', 0)),
                    'suspiciousCount': int(summary.get('suspicious_count', 0)),
                    'manualCount': int(summary.get('manual_count', 0)),
                },
                'trendData': trend_data,
                'actionTrendData': action_trend_data,
                'records': records
            }
        })
        
    except Exception as e:
        logger.error(f"Dashboard API error: {str(e)}", exc_info=True)
        return jsonify({
            'code': 500,  # 新增：错误码
            'success': False,
            'message': f'服务器内部错误：{str(e)}',  # 新增：错误信息
            'error': str(e)
        }), 500
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()