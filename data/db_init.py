import os
import pymysql
import pymysql.cursors
from dbutils.pooled_db import PooledDB
from datetime import datetime, timedelta
from dotenv import load_dotenv
from src.utils.logger import logger

# 加载环境变量
load_dotenv()

# ==================== 1. 初始化全局连接池 ====================
# 将连接池定义为全局变量，确保在多线程/多进程环境下单例运行
_db_pool = None

def init_db_pool():
    """
    初始化连接池，仅在系统启动时运行一次。
    用于业务高并发阶段（API调用、Celery任务等）。
    """
    global _db_pool
    if _db_pool is not None:
        return

    db_params = {
        "host": os.getenv("MYSQL_HOST", "localhost"),
        "port": int(os.getenv("MYSQL_PORT", 3306)),
        "user": os.getenv("MYSQL_USER", "root"),
        "password": os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("MYSQL_DATABASE", "phishing_detection"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "autocommit": True,
        "init_command": "SET time_zone = '+08:00'" 
    }

    try:
        _db_pool = PooledDB(
            creator=pymysql,      # 使用 pymysql 驱动
            maxconnections=50,    # 连接池允许的最大并发连接数
            mincached=5,          # 初始化时，池中至少保持的空闲连接数
            maxcached=20,         # 池中最多闲置连接数
            maxshared=0,          # 对pymysql通常设为0
            blocking=True,        # 连接池满时，新请求阻塞等待
            **db_params
        )
        logger.info(f"✅ 数据库连接池已初始化，最大容量: 50")
    except Exception as e:
        logger.error(f"❌ 初始化数据库连接池失败: {str(e)}")
        raise

def get_db_connection(use_db=True):
    """
    从连接池中获取一个连接（业务运行期间使用）。
    """
    global _db_pool
    if _db_pool is None:
        init_db_pool()
    
    try:
        return _db_pool.connection()
    except Exception as e:
        logger.error(f"❌ 从池中获取连接失败: {str(e)}")
        raise

# ==================== 2. 原始连接管理（仅用于数据库初始化阶段） ====================

def get_raw_connection_without_db():
    """
    专门用于检测/创建数据库，不使用连接池。
    """
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        charset="utf8mb4",
        autocommit=True
    )

def check_database_exists(db_name):
    """检测数据库是否存在"""
    conn = None
    try:
        conn = get_raw_connection_without_db()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
                (db_name,)
            )
            exists = cursor.fetchone() is not None
            return exists
    except Exception as e:
        logger.error(f"❌ 检测数据库是否存在失败：{str(e)}")
        raise
    finally:
        if conn: conn.close()

def create_database(db_name):
    """创建数据库"""
    conn = None
    try:
        conn = get_raw_connection_without_db()
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
            logger.info(f"✅ 数据库 {db_name} 创建成功")
    except Exception as e:
        logger.error(f"❌ 创建数据库失败：{str(e)}")
        raise
    finally:
        if conn: conn.close()

# ==================== 3. 初始化主逻辑 ====================

def create_database_and_tables():
    """
    创建数据库和所有表结构。
    初始化阶段统一使用 raw 连接，避免连接池初始化依赖问题。
    """
    conn = None
    try:
        db_name = os.getenv("MYSQL_DATABASE", "phishing_detection")
        
        # 1. 检测并创建数据库
        if not check_database_exists(db_name):
            create_database(db_name)
        
        # 2. 获取原始连接并切换到目标数据库进行建表
        conn = get_raw_connection_without_db()
        with conn.cursor() as cursor:
            # 物理切换到目标库
            cursor.execute(f"USE {db_name};")
            # 设置时区（确保初始化时的 timestamp 也是东八区）
            cursor.execute("SET time_zone = '+08:00';")

            # --- 创建邮件数据主表 ---
            create_email_table_sql = """
            CREATE TABLE IF NOT EXISTS email_data (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email_id VARCHAR(100) NOT NULL UNIQUE COMMENT '邮件唯一ID',
                sender VARCHAR(255) COMMENT '发件人',
                recipient VARCHAR(255) COMMENT '收件人',
                subject VARCHAR(500) COMMENT '邮件标题',
                send_time DATETIME COMMENT '发送时间',
                content_text LONGTEXT COMMENT '邮件正文（纯文本）',
                client_ip VARCHAR(50) COMMENT '发送方IP',
                from_domain VARCHAR(255) COMMENT '发件人域名',
                header_list LONGTEXT COMMENT '邮件原始Header信息(JSON数组字符串)',
                url_list LONGTEXT COMMENT '原始URL列表(JSON数组字符串)',
                attachment_list LONGTEXT COMMENT '原始附件列表(JSON数组字符串)',
                vt_url_result TINYINT COMMENT 'URL的VT检测最终结果',
                vt_ip_result TINYINT COMMENT 'IP的VT检测最终结果',
                vt_file_result TINYINT COMMENT '附件/文件的VT检测最终结果',
                sandbox_result TINYINT COMMENT '沙箱最终判断：0正常 1可疑 2恶意',
                ai_result TINYINT COMMENT 'AI最终判断:0正常 1可疑 2钓鱼',
                ai_reason TEXT COMMENT 'AI分析详细理由',
                manual_review BOOLEAN DEFAULT FALSE COMMENT '是否人工审核',
                manual_result TINYINT COMMENT '人工审核结果：0正常 1钓鱼 2可疑',
                final_decision TINYINT COMMENT '系统最终决策：0正常 1钓鱼 2可疑',
                is_alert BOOLEAN DEFAULT FALSE COMMENT '是否告警',
                is_block BOOLEAN DEFAULT FALSE COMMENT '是否拦截',
                label TINYINT COMMENT '实际标签: 1钓鱼 0正常',
                phishing_type VARCHAR(50) COMMENT '钓鱼类型',
                data_version INT DEFAULT 1 COMMENT '数据版本',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_label (label),
                INDEX idx_sender (sender),
                INDEX idx_send_time (send_time)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='钓鱼邮件检测统一数据表';
            """
            cursor.execute(create_email_table_sql)
            logger.info("✅ email_data 表已处理")

            # --- 创建数据版本管理表 ---
            create_version_table_sql = """
            CREATE TABLE IF NOT EXISTS data_version (
                version_id INT AUTO_INCREMENT PRIMARY KEY,
                version_desc VARCHAR(500) NOT NULL COMMENT '版本描述',
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE COMMENT '是否当前活跃版本',
                INDEX idx_is_active (is_active)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='数据版本管理表';
            """
            cursor.execute(create_version_table_sql)
            logger.info("✅ data_version 表已处理")
        
        logger.info("🎉 数据库表结构初始化/验证完成！")

    except Exception as e:
        logger.error(f"❌ 数据库初始化失败：{str(e)}", exc_info=True)
        raise
    finally:
        if conn:
            conn.close()
            logger.info("🔌 初始化阶段临时连接已关闭")

if __name__ == "__main__":
    try:
        create_database_and_tables()
        logger.info("✅ 数据库脚本执行成功")
    except Exception as e:
        exit(1)