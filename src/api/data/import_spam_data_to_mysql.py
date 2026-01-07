"""
垃圾邮件数据导入API
路径: src/api/data/import_spam_api.py
接口: POST /api/data/import_spam
"""

import re
import json
import uuid
import pymysql
import pandas as pd
from dotenv import load_dotenv
from email import message_from_string
from email.utils import parsedate_to_datetime
import os
import sys
from typing import List, Dict, Tuple
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import tempfile

# 添加项目根目录到Python路径
current_file = os.path.abspath(__file__)
data_dir = os.path.dirname(current_file)  # src/api/data
api_dir = os.path.dirname(data_dir)  # src/api
src_dir = os.path.dirname(api_dir)  # src
project_root = os.path.dirname(src_dir)  # 项目根目录

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.logger import logger
from data.db_init import get_db_connection

# ===================== 基础配置 =====================
load_dotenv()

BATCH_SIZE = 100
MAX_CONTENT_LENGTH = 65535
ALLOWED_EXTENSIONS = {'csv'}

# 创建蓝图
import_spam_bp = Blueprint('import_spam', __name__)

# ===================== 核心函数 =====================
def allowed_file(filename):
    """检查文件类型"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def read_spam_csv(file_path: str) -> List[Tuple[str, str]]:
    """读取CSV文件"""
    try:
        df = pd.read_csv(
            file_path,
            encoding="latin-1",
            quotechar='"',
            escapechar="\\",
            on_bad_lines="skip",
            dtype={"target": str}
        )
        
        if "text" not in df.columns or "target" not in df.columns:
            raise ValueError("CSV必须包含 'text' 和 'target' 列")
        
        df = df.dropna(subset=["text", "target"])
        df["text"] = df["text"].astype(str).str.strip()
        df["target"] = df["target"].astype(str).str.strip()
        df = df[df["text"].str.len() > 50]
        df = df[df["target"].isin(["0", "1"])]
        
        data = []
        for _, row in df.iterrows():
            email_content = row["text"]
            # 修复1：label值从字符串"phishing/normal"改为数字1/0（匹配email_data表的label字段）
            label = 1 if row["target"] == "1" else 0
            data.append((email_content, label))
        
        logger.info(f"✅ 成功读取CSV，有效数据：{len(data)}条")
        return data
    
    except Exception as e:
        logger.error(f"❌ 读取CSV失败：{str(e)}", exc_info=True)
        raise


def preprocess_mbox_format(raw_content: str) -> str:
    """预处理mbox格式"""
    header_pattern = r'(\b(?:Return-Path|Delivered-To|Received|Date|From|To|Subject|Message-Id|MIME-Version|Content-Type|Content-Transfer-Encoding|X-[\w-]+|In-Reply-To|References|Sender|Errors-To|List-[\w-]+|Reply-To|Cc|Bcc|User-Agent|X-Mailer|Importance|Priority):\s*)'
    formatted = re.sub(header_pattern, r'\n\1', raw_content, flags=re.IGNORECASE)
    formatted = re.sub(r'\n{2,}', '\n', formatted).strip()
    return formatted


def extract_urls(text: str) -> List[str]:
    """提取文本中的所有URL"""
    if not text:
        return []
    url_pattern = r'https?://[^\s<>"\'\)]+|www\.[^\s<>"\'\)]+'
    urls = re.findall(url_pattern, text, re.IGNORECASE)
    return list(set([url[:500] for url in urls if len(url) < 500]))


def parse_email_optimized(raw_content: str, label: str) -> Dict:
    """最优邮件解析方案"""
    try:
        formatted_content = preprocess_mbox_format(raw_content)
        msg = message_from_string(formatted_content)
        
        sender = "unknown"
        from_header = msg.get("From", "")
        if from_header:
            email_match = re.search(r'[\w\.\-]+@[\w\.\-]+\.\w+', from_header)
            if email_match:
                sender = email_match.group(0)
        
        recipient = "unknown"
        to_header = msg.get("To", "")
        if to_header:
            email_match = re.search(r'[\w\.\-]+@[\w\.\-]+\.\w+', to_header)
            if email_match:
                recipient = email_match.group(0)
        
        subject = msg.get("Subject", "no subject").strip()
        if not subject:
            subject = "no subject"
        
        send_time = None
        date_header = msg.get("Date", "")
        if date_header:
            try:
                send_time = parsedate_to_datetime(date_header)
            except:
                pass
        
        content_text = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            content_text = payload.decode('utf-8', errors='ignore')
                            break
                    except Exception as e:
                        logger.debug(f"解码multipart失败：{e}")
                        continue
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    content_text = payload.decode('utf-8', errors='ignore')
                else:
                    payload_str = msg.get_payload()
                    if isinstance(payload_str, str):
                        content_text = payload_str
            except Exception as e:
                logger.debug(f"解码单部分失败：{e}")
                try:
                    content_text = str(msg.get_payload())
                except:
                    pass
        
        if not content_text or len(content_text.strip()) < 20:
            body_match = re.search(r'\n\s*\n(.+)', formatted_content, re.DOTALL)
            if body_match:
                content_text = body_match.group(1).strip()
            else:
                content_text = raw_content
        
        lines = content_text.split('\n')
        clean_lines = []
        for line in lines:
            if re.match(r'^[A-Za-z\-]+:\s*', line):
                continue
            clean_lines.append(line)
        
        content_text = '\n'.join(clean_lines)
        content_text = re.sub(r'[\x00-\x1F\x7F]', '', content_text)
        content_text = re.sub(r'\n{3,}', '\n\n', content_text)
        content_text = content_text.strip()
        
        if len(content_text) > MAX_CONTENT_LENGTH:
            content_text = content_text[:MAX_CONTENT_LENGTH]
        
        urls = extract_urls(content_text)
        # 修复2：字段名从url_links_json改为url_list_json（匹配email_data表的url_list字段）
        url_list_json = json.dumps(urls, ensure_ascii=False) if urls else None
        
        return {
            # 修复3：key名从email_uuid改为email_id（匹配email_data表的email_id字段）
            "email_id": str(uuid.uuid4()),
            "sender": sender[:255],
            "recipient": recipient[:255],
            "subject": subject[:500],
            "send_time": send_time,
            "label": label,
            "content_text": content_text or "no content",
            # 修复4：字段名从url_links改为url_list（匹配email_data表的url_list字段）
            "url_list": url_list_json
        }
    
    except Exception as e:
        logger.warning(f"⚠️ 邮件解析失败：{str(e)}")
        return {
            # 修复3：key名从email_uuid改为email_id
            "email_id": str(uuid.uuid4()),
            "sender": "parse_failed",
            "recipient": "unknown",
            "subject": "parse error",
            "send_time": None,
            "label": label,
            "content_text": raw_content[:MAX_CONTENT_LENGTH],
            # 修复4：字段名从url_links改为url_list
            "url_list": None
        }


def batch_write_to_mysql(parsed_data: List[Dict]):
    """批量写入数据库"""
    if not parsed_data:
        logger.warning("⚠️ 无有效数据可写入")
        return 0
    
    valid_data = [d for d in parsed_data if d is not None]
    if not valid_data:
        logger.warning("⚠️ 过滤后无有效数据")
        return 0
    
    conn = None
    try:
        conn = get_db_connection(use_db=True)
        cursor = conn.cursor()
        
        # 修复5：删除SQL中不存在的has_attachment/attachment_count字段
        insert_sql = """
        INSERT IGNORE INTO email_data (
            email_id, sender, recipient, subject, send_time, 
            label, content_text, url_list, data_version
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        total = len(valid_data)
        success_count = 0
        
        for i in range(0, total, BATCH_SIZE):
            batch = valid_data[i:i+BATCH_SIZE]
            batch_data = [
                (
                    # 修复6：取值从d["email_uuid"]改为d["email_id"]
                    d["email_id"],
                    d["sender"],
                    d["recipient"],
                    d["subject"],
                    d["send_time"],
                    d["label"],
                    d["content_text"],
                    # 修复7：取值从d["url_links"]改为d["url_list"]
                    d["url_list"],
                    1  # data_version固定值
                ) for d in batch
            ]
            
            try:
                cursor.executemany(insert_sql, batch_data)
                conn.commit()
                success_count += len(batch)
                logger.info(f"📤 批次 {i//BATCH_SIZE + 1}：已插入 {len(batch)} 条，累计 {success_count}/{total}")
            except pymysql.MySQLError as e:
                conn.rollback()
                logger.error(f"❌ 批次 {i//BATCH_SIZE + 1} 失败：{e.args[1]}")
                continue
        
        logger.info(f"🎉 入库完成：成功 {success_count}/{total} 条")
        return success_count
    
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"❌ 批量写入失败：{str(e)}", exc_info=True)
        raise
    finally:
        if conn:
            cursor.close()
            conn.close()


# ===================== API路由 =====================

@import_spam_bp.route('/import_spam', methods=['POST'])
def import_spam():
    """
    导入垃圾邮件数据API
    请求: multipart/form-data
    参数: file (CSV文件)
    """
    try:
        # 默认使用服务器上的文件
        file_path = os.path.join(project_root, "data", "spam_assassin.csv")
        
        # 读取CSV
        raw_data = read_spam_csv(file_path)
        
        # 解析邮件
        logger.info("开始解析邮件...")
        parsed_data = []
        for idx, (content, label) in enumerate(raw_data):
            if idx % 500 == 0:
                logger.info(f"🔍 已解析 {idx}/{len(raw_data)} 封")
            parsed_email = parse_email_optimized(content, label)
            parsed_data.append(parsed_email)
        
        # 写入数据库
        success_count = batch_write_to_mysql(parsed_data)
        
        logger.info("✅ 全部流程完成！")
        
        return jsonify({
            'success': True,
            'total': len(raw_data),
            'success_count': success_count,
            'message': f'导入完成！成功 {success_count}/{len(raw_data)} 条'
        }), 200
    
    except Exception as e:
        logger.error(f"❌ 导入失败：{str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'message': f'导入失败: {str(e)}'
        }), 500