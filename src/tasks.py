import email,hashlib,re,os,smtplib,json,requests,time,quopri
from datetime import datetime  # 补充缺失的导入
from email.utils import getaddresses, parseaddr, parsedate_to_datetime  # 补充parsedate_to_datetime
from email.header import decode_header
from celery_app import celery_app
from src.utils.logger import logger
from config.settings import get_bool
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


SMTP_RELAY_HOST = os.getenv("SMTP_RELAY_HOST", "localhost")
SMTP_RELAY_PORT = int(os.getenv("SMTP_RELAY_PORT", 2525))
API_BASE_URL = "http://localhost:8000/api"

# ==================== 邮件解析工具 ====================
def decode_mime_header(value: str) -> str:
    if not value:
        return ""
    decoded_parts = decode_header(value)
    result = ""
    for text, charset in decoded_parts:
        if isinstance(text, bytes):
            try:
                result += text.decode(charset or "utf-8", errors="ignore")
            except Exception:
                result += text.decode("utf-8", errors="ignore")
        else:
            result += text
    return result.strip()

def parse_sender(header_value: str):
    name, addr = parseaddr(header_value)
    name = decode_mime_header(name)
    return name, addr

def parse_recipients(header_values):
    """
    解析邮件收件人列表，支持 MIME 编码和多收件人
    修复：不再手动拆分逗号，直接使用 getaddresses 处理原始字符串
    """
    recipients = []
    if not header_values:
        return recipients

    # 关键修复：将所有header值拼接成一个字符串，直接交给getaddresses处理
    # getaddresses 会自动处理逗号分隔、MIME编码等情况
    full_address_str = ', '.join(header_values)
    
    # getaddresses 处理 (name, email) 元组（自动处理MIME编码和分隔符）
    addr_tuples = getaddresses([full_address_str])

    for name, email_addr in addr_tuples:
        if email_addr:
            # 清理邮箱地址，确保格式正确
            email_addr = email_addr.lower().strip()
            # 验证邮箱格式（简单校验）
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email_addr):
                recipients.append({
                    "name": decode_mime_header(name),
                    "email": email_addr
                })
    
    logger.info(f"解析到有效收件人数量: {len(recipients)}")
    return recipients

def parse_email_date(message):
    """解析邮件发送时间"""
    raw_date = message.get("Date")
    if not raw_date:
        return None
    try:
        return parsedate_to_datetime(raw_date)
    except Exception:
        return None

def extract_email_content(message):
    """解析邮件正文（支持 multipart / quoted-printable / html）"""
    text_parts = []
    html_parts = []

    for part in message.walk():
        if part.get_content_maintype() != "text":
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        charset = part.get_content_charset() or "utf-8"

        try:
            # 解码 quoted-printable
            if part.get('Content-Transfer-Encoding', '').lower() == 'quoted-printable':
                payload = quopri.decodestring(payload)
            text = payload.decode(charset, errors="ignore")
        except Exception:
            text = payload.decode("utf-8", errors="ignore")

        if part.get_content_type() == "text/plain":
            text_parts.append(text)
        elif part.get_content_type() == "text/html":
            html_parts.append(text)

    if text_parts:
        return "\n".join(text_parts)
    if html_parts:
        return "\n".join(html_parts)

    return "(Processing...)"


# ==================== 邮件通知函数 ====================
def send_alert_notification(email_id, risk_level, sender_email, subject, reason, notify_email):
    """
    发送告警通知邮件
    :param email_id: 邮件ID
    :param risk_level: 风险等级 (1=可疑, 2=恶意)
    :param sender_email: 原始发件人
    :param subject: 原始主题
    :param reason: AI分析原因
    :param notify_email: 通知邮箱地址
    """
    try:
        # 构建告警邮件
        msg = MIMEMultipart('alternative')
        msg['From'] = "security-alert@hyinfo.cc"
        msg['To'] = notify_email
        msg['Subject'] = f"[安全告警] 检测到{'可疑' if risk_level == 1 else '恶意'}邮件"
        
        # 邮件正文（HTML格式）
        risk_badge = "⚠️ 可疑邮件" if risk_level == 1 else "🚨 恶意邮件"
        risk_color = "#FFA500" if risk_level == 1 else "#FF0000"
        
        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: {risk_color}; color: white; padding: 15px; border-radius: 5px; }}
                .content {{ background-color: #f9f9f9; padding: 20px; margin-top: 20px; border-radius: 5px; }}
                .field {{ margin-bottom: 15px; }}
                .label {{ font-weight: bold; color: #333; }}
                .value {{ color: #666; margin-top: 5px; }}
                .footer {{ margin-top: 20px; font-size: 12px; color: #999; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{risk_badge}</h2>
                </div>
                <div class="content">
                    <div class="field">
                        <div class="label">邮件ID:</div>
                        <div class="value">{email_id}</div>
                    </div>
                    <div class="field">
                        <div class="label">风险等级:</div>
                        <div class="value">Level {risk_level} - {'可疑邮件' if risk_level == 1 else '恶意邮件'}</div>
                    </div>
                    <div class="field">
                        <div class="label">发件人:</div>
                        <div class="value">{sender_email}</div>
                    </div>
                    <div class="field">
                        <div class="label">邮件主题:</div>
                        <div class="value">{subject}</div>
                    </div>
                    <div class="field">
                        <div class="label">检测原因:</div>
                        <div class="value">{reason}</div>
                    </div>
                    <div class="field">
                        <div class="label">检测时间:</div>
                        <div class="value">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
                    </div>
                </div>
                <div class="footer">
                    <p>此邮件由安全系统自动发送，请勿回复。</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # 纯文本版本（备用）
        text_content = f"""
        {risk_badge}
        
        邮件ID: {email_id}
        风险等级: Level {risk_level} - {'可疑邮件' if risk_level == 1 else '恶意邮件'}
        发件人: {sender_email}
        邮件主题: {subject}
        检测原因: {reason}
        检测时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        
        ---
        此邮件由安全系统自动发送，请勿回复。
        """
        
        # 添加邮件正文
        part_text = MIMEText(text_content, 'plain', 'utf-8')
        part_html = MIMEText(html_content, 'html', 'utf-8')
        msg.attach(part_text)
        msg.attach(part_html)
        
        # 发送邮件
        with smtplib.SMTP(SMTP_RELAY_HOST, SMTP_RELAY_PORT, timeout=30) as smtp:
            smtp.ehlo()
            if SMTP_RELAY_PORT == 587:
                smtp.starttls()
                smtp.ehlo()
            smtp.send_message(msg)
        
        logger.info(f"✅ 告警通知已发送到: {notify_email}")
        return True
        
    except Exception as e:
        logger.error(f"❌ 发送告警通知失败: {e}", exc_info=True)
        return False

# ==================== 邮件检测引擎 ====================
class DetectionEngine:
    """邮件检测引擎"""
    
    @staticmethod
    def extract_urls(content):
        if not content:
            return []
        urls = list(set(re.findall(r'https?://[^\s<>"\']+', content)))
        if urls:
            logger.info(f"提取到 {len(urls)} 个URL")
        return urls

    @staticmethod
    def parse_attachments(message):
        hashes = []
        attachments = []
        for part in message.walk():
            filename = part.get_filename()
            if filename:
                payload = part.get_payload(decode=True)
                if payload:
                    file_hash = hashlib.md5(payload).hexdigest()
                    hashes.append(file_hash)
                    attachments.append({
                        "filename": filename,
                        "content_type": part.get_content_type(),
                        "size": len(payload),
                        "file_hash": file_hash
                    })
        if attachments:
            logger.info(f"解析到 {len(attachments)} 个附件")
        return hashes, attachments

    @staticmethod
    def extract_email_content(message):
        return extract_email_content(message)

    @staticmethod
    def calculate_threat_risk(threat_result):
        vt_url_result = vt_ip_result = vt_file_result = 0
        try:
            # 1. 域名风险
            domains_data = threat_result.get("results", {}).get("domains", {})
            if domains_data:
                domain_info = next(iter(domains_data.values()))
                if "data" in domain_info:
                    attrs = domain_info["data"]["attributes"]
                    malicious = attrs.get("last_analysis_stats", {}).get("malicious", 0)
                    suspicious = attrs.get("last_analysis_stats", {}).get("suspicious", 0)
                    categories = attrs.get("categories", {})
                    risk_tags = [v for v in categories.values() 
                                 if any(tag in v.lower() for tag in ["spam", "phishing", "malicious", "malware"])]
                    reputation = attrs.get("reputation", 0)
                    first_submit = attrs.get("first_submission_date", 0)
                    is_new_domain = 1 if (int(time.time()) - first_submit) <= 7 * 24 * 3600 else 0
                    total = (malicious * 5) + (suspicious * 2) + (len(risk_tags) * 3) + \
                            (reputation * -0.01 if reputation <= 0 else 0) + (is_new_domain * 2)
                    if total >= 6:
                        vt_url_result = 2
                    elif 3 <= total < 6:
                        vt_url_result = 1
                    logger.info(f"域名风险评分: {total:.2f}, 结果: {vt_url_result}")

            # 2. IP风险
            ips_data = threat_result.get("results", {}).get("ips", {})
            if ips_data:
                ip_info = next(iter(ips_data.values()))
                if "data" in ip_info:
                    attrs = ip_info["data"]["attributes"]
                    malicious = attrs.get("last_analysis_stats", {}).get("malicious", 0)
                    suspicious = attrs.get("last_analysis_stats", {}).get("suspicious", 0)
                    threat_ctx = len(attrs.get("crowdsourced_context", []))
                    reputation = attrs.get("reputation", 0)
                    as_owner = attrs.get("as_owner", "").lower()
                    trusted_providers = ["google", "aliyun", "tencent", "huawei", "amazon", "microsoft"]
                    is_irregular_as = 0 if any(provider in as_owner for provider in trusted_providers) else 1
                    total = (malicious * 5) + (suspicious * 2) + (threat_ctx * 4) + \
                            ((500 - reputation) * 0.001 if reputation <= 500 else 0) + (is_irregular_as * 3)
                    if total >= 8:
                        vt_ip_result = 2
                    elif 4 <= total < 8:
                        vt_ip_result = 1
                    logger.info(f"IP风险评分: {total:.2f}, 结果: {vt_ip_result}")

            # 3. 文件哈希风险
            hashes_data = threat_result.get("results", {}).get("hashes", {})
            if hashes_data:
                hash_info = next(iter(hashes_data.values()))
                if "error" in hash_info and "404" in str(hash_info["error"]):
                    vt_file_result = 0
                    logger.info("文件哈希未在VirusTotal库中找到")
                elif "data" in hash_info:
                    attrs = hash_info["data"]["attributes"]
                    malicious = attrs.get("last_analysis_stats", {}).get("malicious", 0)
                    suspicious = attrs.get("last_analysis_stats", {}).get("suspicious", 0)
                    threat_names = len(attrs.get("threat_names", []))
                    reputation = attrs.get("reputation", 0)
                    total = (malicious * 6) + (suspicious * 2) + (threat_names * 5) + \
                            (reputation * -0.02 if reputation <= 0 else 0)
                    if total >= 9:
                        vt_file_result = 2
                    elif 4 <= total < 9:
                        vt_file_result = 1
                    logger.info(f"文件风险评分: {total:.2f}, 结果: {vt_file_result}")

        except Exception as e:
            logger.error(f"计算威胁风险异常: {e}")
        return vt_url_result, vt_ip_result, vt_file_result

    @staticmethod
    def parse_ai_result(ai_response):
        try:
            ai_analysis = ai_response.get("data", {}).get("ai_analysis", {})
            if isinstance(ai_analysis, dict) and "result" in ai_analysis:
                return ai_analysis
            if isinstance(ai_analysis, str):
                clean_text = ai_analysis.strip()
                if clean_text.startswith("```json"):
                    clean_text = clean_text[7:]
                if clean_text.startswith("```"):
                    clean_text = clean_text[3:]
                if clean_text.endswith("```"):
                    clean_text = clean_text[:-3]
                clean_text = clean_text.strip()
                parsed = json.loads(clean_text)
                if isinstance(parsed, dict) and "result" in parsed:
                    return parsed
            logger.warning(f"AI返回格式异常: {ai_analysis}")
            return {"result": 0, "reason": "AI返回格式错误", "confidence": 0}
        except json.JSONDecodeError as e:
            logger.error(f"AI结果JSON解析失败: {e}")
            return {"result": 0, "reason": "JSON解析失败", "confidence": 0}
        except Exception as e:
            logger.error(f"解析AI结果异常: {e}")
            return {"result": 0, "reason": "解析异常", "confidence": 0}

    @staticmethod
    def modify_email_subject(message, ai_result):
        try:
            if ai_result > 0:
                prefix = "[⚠️可疑]" if ai_result == 1 else "[🚨恶意]"
                raw_subject = message.get('Subject', '(无主题)')
                subject = decode_mime_header(raw_subject)
                if not subject.startswith(("[⚠️可疑]", "[🚨恶意]")):
                    new_subject = f"{prefix} {subject}"
                    if message.get('Subject'):
                        message.replace_header('Subject', new_subject)
                    else:
                        message.add_header('Subject', new_subject)
                    logger.info(f"邮件主题已修改: {new_subject}")
        except Exception as e:
            logger.error(f"修改邮件主题失败: {e}")

    @staticmethod
    def forward_email(message, email_id):
        try:
            recipients = []
            for header in ['To', 'Cc', 'Bcc']:
                header_values = message.get_all(header, [])
                parsed_list = parse_recipients(header_values)
                recipients.extend([r["email"] for r in parsed_list])
            
            # 去重
            recipients = list(dict.fromkeys(recipients))
            
            # 2. 核心补救逻辑：如果 Header 为空，尝试查找信封收件人
            # 在某些代理转发中，收件人可能存储在 'X-Original-To' 或 'Delivered-To'
            if not recipients:
                alt_headers = message.get_all('X-Original-To', []) or message.get_all('Delivered-To', [])
                if alt_headers:
                    # 对备选header也使用标准解析函数
                    parsed_alt = parse_recipients(alt_headers)
                    recipients = [r["email"] for r in parsed_alt]
                    logger.info(f"⚠️ 从备选 Header 提取到收件人: {recipients}")

            if not recipients:
                logger.error(f"❌ 无法从任何 Header 提取收件人: {email_id}")
                # 此处建议根据业务逻辑决定：是丢弃还是转发给管理员？
                return False
            
            raw_from = message.get('From', '')
            sender_name, sender_addr = parse_sender(raw_from)
            # 修复：如果发件人地址为空，使用默认值避免SMTP错误
            if not sender_addr:
                sender_addr = "noreply@hyinfo.cc"
                logger.warning(f"⚠️ 发件人地址为空，使用默认值: {sender_addr}")
                
            logger.info(f"📤 准备转发邮件: {email_id}")
            logger.info(f"   发件人: {sender_addr}")
            logger.info(f"   收件人数量: {len(recipients)}")
            logger.info(f"   收件人列表: {recipients}")
            
            with smtplib.SMTP(SMTP_RELAY_HOST, SMTP_RELAY_PORT, timeout=30) as smtp:
                # 可选：添加EHLO/STARTTLS（如果SMTP服务器需要）
                smtp.ehlo()
                if SMTP_RELAY_PORT == 587:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.send_message(message, sender_addr, recipients)
                
            logger.info(f"✅ 邮件转发成功: {email_id}")
            logger.info(f"   已转发给 {len(recipients)} 个收件人: {', '.join(recipients)}")
            return True
            
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP转发失败: {email_id}, 错误: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 邮件转发异常: {email_id}, 错误: {e}")
            return False

    @staticmethod
    def run_detection(email_id, message, client_ip):
        """
        完整检测流程：
        1. 解析邮件内容
        2. 威胁情报查询（VirusTotal）
        3. 沙箱检测
        4. AI智能分析
        5. 更新数据库
        6. 向量化存储
        7. 邮件转发或拦截
        """
        logger.info(f"========== 开始检测邮件: {email_id} ==========")
        start_time = time.time()
        
        try:
            # ========== 阶段1: 解析邮件内容 ==========
            logger.info("📧 阶段1: 解析邮件内容")
            
            # 提取正文（优化：返回text和html，这里先用text）
            content_text = DetectionEngine.extract_email_content(message)
            
            # 提取URL
            urls = DetectionEngine.extract_urls(content_text)
            
            # 解析附件
            file_hashes, attachments = DetectionEngine.parse_attachments(message)
            
            # 提取发件人（解码MIME）
            from_header = message.get("From", "")
            sender_name, sender_email = parse_sender(from_header)
            # 只保留纯邮箱地址，去掉昵称
            parsed_sender = sender_email  # 直接用纯邮箱地址，不拼接昵称
            
            # 解析主题（解码MIME）
            raw_subject = message.get('Subject', '')
            parsed_subject = decode_mime_header(raw_subject)
            
            # 提取发件人域名
            from_domain = sender_email.split('@')[-1] if '@' in sender_email else ""
            
            # 提前定义 domains/ips 变量（关键修复：避免NameError）
            ips = [client_ip] if client_ip else []
            domains = [from_domain] + urls[:5]  # 限制URL数量
            
            # 解析邮件发送时间（Date头）
            send_time_str = None
            date_header = message.get('Date', '')
            if date_header:
                try:
                    # 解析邮件Date头为datetime对象
                    send_time = parsedate_to_datetime(date_header)
                    # 转换为字符串格式（适配数据库）
                    send_time_str = send_time.strftime('%Y-%m-%d %H:%M:%S')
                except Exception as e:
                    logger.warning(f"解析发送时间失败: {e}")
            # 兜底逻辑：无论是否解析成功，都要有默认值
            if not send_time_str:
                send_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # ========== 更新解析后的邮件内容到数据库 ==========
            logger.info(f"📝 更新邮件解析内容: {email_id}")
            try:
                # 构造更新数据
                update_content_data = {
                    "email_id": email_id,
                    "sender": parsed_sender,       # 纯邮箱地址
                    "subject": parsed_subject,     # 解码后的主题
                    "content_text": content_text,  # 解析后的正文
                    "send_time": send_time_str,    # 发送时间
                    "from_domain": from_domain,    # 发件人域名
                    "url_list": json.dumps(urls),  # URL列表（JSON字符串）
                    "attachment_list": json.dumps(attachments)  # 附件列表（JSON字符串）
                }
                
                # 调用已有的update_email_risk接口（增强健壮性）
                resp = requests.post(
                    f"{API_BASE_URL}/email/update_email_risk",
                    json=update_content_data,
                    headers={"Content-Type": "application/json"},  # 显式指定JSON
                    timeout=10  # 延长超时时间
                )
                
                # 增强日志：打印请求/响应详情
                logger.info(f"更新邮件内容请求: {json.dumps(update_content_data, ensure_ascii=False)}")
                if resp.status_code == 200:
                    resp_json = resp.json()
                    if resp_json.get("success"):
                        logger.info(f"✅ 邮件内容更新成功: {email_id}")
                    else:
                        logger.warning(f"⚠️ 邮件内容更新失败: {resp_json.get('message')}")
                else:
                    logger.error(f"⚠️ 更新邮件内容接口返回异常: 状态码={resp.status_code}, 响应={resp.text}")
            except Exception as e:
                logger.error(f"❌ 更新邮件内容异常: {e}", exc_info=True)
            
            # ========== 原有逻辑继续执行 ==========
            logger.info(f"发件人: {from_header}, 域名: {from_domain}, 客户端IP: {client_ip}")
            # logger.info(f"待检测: 域名×{len(domains)}, 文件×{len(file_hashes)}")

            # ========== 阶段2: 威胁情报查询 ==========
            logger.info("🔍 阶段2: VirusTotal威胁情报查询")
            vt_url_result = vt_ip_result = vt_file_result = 0
            
            try:
                resp = requests.post(
                    f"{API_BASE_URL}/threat/threat_query",
                    json={
                        "ips": ips,
                        "domains": domains,
                        "hashes": file_hashes[:5]  # 限制哈希数量
                    },
                    timeout=15
                )
                
                if resp.status_code == 200:
                    threat_result = resp.json()
                    vt_url_result, vt_ip_result, vt_file_result = \
                        DetectionEngine.calculate_threat_risk(threat_result)
                    
                    logger.info(f"VT检测结果: URL={vt_url_result}, IP={vt_ip_result}, 文件={vt_file_result}")
                else:
                    logger.warning(f"威胁查询返回异常状态码: {resp.status_code}")
                    threat_result = {}
                    
            except requests.Timeout:
                logger.error("威胁查询超时")
                threat_result = {}
            except Exception as e:
                logger.error(f"威胁查询异常: {e}", exc_info=True)
                threat_result = {}

            # 更新威胁字段到数据库
            try:
                requests.post(
                    f"{API_BASE_URL}/email/update_email_risk",
                    json={
                        "email_id": email_id,
                        "vt_url_result": vt_url_result,
                        "vt_ip_result": vt_ip_result,
                        "vt_file_result": vt_file_result
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=5
                )
            except Exception as e:
                logger.warning(f"更新VT结果失败: {e}", exc_info=True)

            # ========== 阶段3: 沙箱检测 ==========
            logger.info("🧪 阶段3: 沙箱检测")
            final_sandbox_result = 0  # 默认值设为0

            try:
                resp = requests.post(
                    f"{API_BASE_URL}/threat/sandbox_query",
                    json={
                        "file_hashes": file_hashes,
                        "domains": domains,
                        "ips": ips
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=30
                )
                
                # 打印完整的沙箱响应日志（关键：排查沙箱接口问题）
                logger.info(f"沙箱检测请求响应: 状态码={resp.status_code}, 内容={resp.text[:1000]}")  # 截断长内容
                
                if resp.status_code == 200:
                    sandbox_data = resp.json()
                    # 关键：兼容None的情况，强制设为0
                    final_sandbox_result = sandbox_data.get("final_sandbox_result", 0)
                    # 处理返回None的情况
                    if final_sandbox_result is None:
                        final_sandbox_result = 0
                        logger.warning(f"⚠️ 沙箱检测结果为None，已重置为0: {email_id}")
                    logger.info(f"沙箱检测结果: {final_sandbox_result}")
                else:
                    logger.error(f"❌ 沙箱查询返回异常状态码: {resp.status_code}, 响应内容: {resp.text}")
                    
            except requests.Timeout:
                logger.error(f"❌ 沙箱查询超时: email_id={email_id}")
            except json.JSONDecodeError as e:
                logger.error(f"❌ 沙箱响应JSON解析失败: {e}, 响应内容: {resp.text}", exc_info=True)
            except Exception as e:
                logger.error(f"❌ 沙箱检测异常: {e}", exc_info=True)
                # 打印完整堆栈信息
                import traceback
                logger.error(f"沙箱检测异常堆栈: {traceback.format_exc()}")

            # ========== 阶段4: AI智能分析 ==========
            logger.info("🤖 阶段4: AI智能分析")
            ai_result = 0
            ai_analysis = {}

            try:
                resp = requests.post(
                    f"{API_BASE_URL}/ai/aichat",
                    json={"email_id": email_id},
                    headers={"Content-Type": "application/json"},
                    timeout=60
                )
                
                if resp.status_code == 200:
                    ai_response = resp.json()
                    ai_analysis = DetectionEngine.parse_ai_result(ai_response)
                    ai_result = ai_analysis.get("result", 0)
                    
                    logger.info(f"AI分析结果={ai_result}, 置信度={ai_analysis.get('confidence', 0)}")
                else:
                    logger.warning(f"AI分析返回异常状态码: {resp.status_code}, 响应内容: {resp.text}")
                    
            except requests.Timeout:
                logger.error("AI分析超时")
            except Exception as e:
                logger.error(f"AI分析异常: {e}", exc_info=True)

            # ========== 阶段5: 更新数据库 ==========
            logger.info("💾 阶段5: 更新检测结果")

            try:
                # 构建更新数据
                update_data = {
                    "email_id": email_id,
                    "sandbox_result": final_sandbox_result,
                    "ai_result": ai_result,
                    "ai_reason": ai_analysis.get("reason", ""),
                    "phishing_type": ai_analysis.get("phishing_type", ""),
                    "final_decision": ai_result
                }
                
                # 调用更新接口
                update_resp = requests.post(
                    f"{API_BASE_URL}/email/update_email_risk",
                    json=update_data,
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                
                # 打印更新响应日志
                logger.info(f"更新检测结果响应: 状态码={update_resp.status_code}, 内容={update_resp.text}")
                
                if update_resp.status_code == 200:
                    update_json = update_resp.json()
                    if update_json.get("success"):
                        logger.info(f"✅ 检测结果更新成功: {email_id}")
                    else:
                        logger.warning(f"⚠️ 检测结果更新失败: {update_json.get('message')}")
                else:
                    logger.error(f"❌ 检测结果更新接口返回异常: {update_resp.status_code}")
                    
            except Exception as e:
                logger.error(f"更新检测结果失败: {e}", exc_info=True)

            # ========== 阶段6: 向量化存储 ==========
            logger.info("🔢 阶段6: 向量化存储")
            
            try:
                resp = requests.post(
                    f"{API_BASE_URL}/data/save_email_to_chroma_by_id",
                    json={"email_id": email_id},
                    headers={"Content-Type": "application/json"},
                    timeout=10
                )
                
                if resp.status_code != 200:
                    logger.warning(f"向量存储返回状态码: {resp.status_code}")
                    
            except requests.Timeout:
                logger.error("向量存储超时")
            except Exception as e:
                logger.warning(f"向量存储失败: {e}", exc_info=True)

            # ========== 阶段7: 邮件转发或拦截 ==========
            logger.info("📮 阶段7: 邮件转发决策")
            
            def load_config():
                """读取现有config.json配置，适配原始格式（动态获取项目根目录）"""
                try:
                    current_file = os.path.abspath(__file__)
                    # tasks.py 在 src/ 目录,需要向上一级才是项目根目录
                    src_dir = os.path.dirname(current_file)  # /project/MyPhishing/src
                    project_root = os.path.dirname(src_dir)  # /project/MyPhishing ✅
                    
                    # 拼接配置文件路径
                    config_path = os.path.join(project_root, "config", "config.json")
                    
                    # 打印路径用于调试
                    logger.info(f"📁 配置文件路径: {config_path}")
                    
                    # 读取配置文件
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    
                    # ========== 关键修改：只对布尔字段进行转换 ==========
                    # 定义布尔字段列表
                    BOOL_FIELDS = [
                        "EMAIL_INTERCEPT_ENABLED_1",
                        "EMAIL_ALERT_ENABLED_1",
                        "EMAIL_INTERCEPT_ENABLED_2",
                        "EMAIL_ALERT_ENABLED_2"
                    ]
                    
                    # 只对布尔字段进行字符串到布尔值的转换
                    for key in BOOL_FIELDS:
                        if key in config and isinstance(config[key], str):
                            config[key] = config[key].lower() == "true"
                    
                    # 确保 NOTIFICATION_EMAIL 是字符串类型
                    if "NOTIFICATION_EMAIL" in config:
                        if not isinstance(config["NOTIFICATION_EMAIL"], str):
                            config["NOTIFICATION_EMAIL"] = ""
                    
                    logger.info(f"✅ 配置文件读取成功: {config}")
                    return config
                except FileNotFoundError:
                    logger.error(f"❌ 配置文件不存在: {config_path}")
                    return {}
                except Exception as e:
                    logger.error(f"❌ 读取配置文件失败: {str(e)}")
                    return {}
                
                except FileNotFoundError:
                    logger.error(f"❌ 配置文件不存在: {config_path}")
                    # 返回默认配置
                    return {
                        "EMAIL_INTERCEPT_ENABLED_1": False,
                        "EMAIL_ALERT_ENABLED_1": True,
                        "EMAIL_INTERCEPT_ENABLED_2": True,
                        "EMAIL_ALERT_ENABLED_2": True,
                        "NOTIFICATION_EMAIL": ""  # 默认为空
                    }
                except Exception as e:
                    logger.error(f"❌ 读取配置文件异常: {e}", exc_info=True)
                    return {
                        "EMAIL_INTERCEPT_ENABLED_1": True,
                        "EMAIL_ALERT_ENABLED_1": True,
                        "EMAIL_INTERCEPT_ENABLED_2": True,
                        "EMAIL_ALERT_ENABLED_2": True,
                        "NOTIFICATION_EMAIL": ""
                    }

            config = load_config()
            risk_level = ai_result  # 当前邮件的风险等级

            # 获取通知邮箱配置（增加容错处理）
            notification_email = config.get("NOTIFICATION_EMAIL", "")
            # 处理可能的布尔值或其他类型
            if not isinstance(notification_email, str):
                notification_email = ""
            notification_email = notification_email.strip()
            
            # ========== 关键修改2：动态匹配配置项 ==========
            # 根据风险等级拼接配置key（完全适配你的原始配置）
            intercept_config_key = f"EMAIL_INTERCEPT_ENABLED_{risk_level}"
            alert_config_key = f"EMAIL_ALERT_ENABLED_{risk_level}"

            # 获取配置值（兜底：风险等级0/3等默认不拦截）
            intercept_enabled = config.get(intercept_config_key, False)
            alert_enabled = config.get(alert_config_key, True)

            # 打印配置检查日志（便于调试）
            logger.info(f"📋 拦截配置检查: 风险等级={risk_level}, 拦截开关={intercept_config_key}={intercept_enabled}, 告警开关={alert_config_key}={alert_enabled}")

            # ========== 初始化告警和拦截状态 ==========
            is_alert = False  # 是否触发了告警
            is_block = False  # 是否触发了拦截

            if intercept_enabled:
                logger.warning(f"🚫 邮件已拦截: {email_id} (风险等级: {risk_level})")
                is_block = True  # 标记为已拦截
                
                # 触发告警（如果开启）
                if alert_enabled and notification_email:
                    logger.info(f"📧 发送告警通知: {email_id} (风险等级: {risk_level}) -> {notification_email}")
                    
                    
                    # 发送告警邮件
                    send_alert_notification(
                        email_id=email_id,
                        risk_level=risk_level,
                        sender_email=parsed_sender,  # 使用之前解析的发件人
                        subject=parsed_subject,      # 使用之前解析的主题
                        reason=ai_analysis.get("reason", "未知原因"),
                        notify_email=notification_email
                    )
                    is_alert = True  # 标记为已告警
                elif alert_enabled and not notification_email:
                    logger.warning(f"⚠️ 告警已启用但未配置通知邮箱，无法发送通知")
                
                # ========== 更新拦截和告警状态到数据库 ==========
                try:
                    update_resp = requests.post(
                        f"{API_BASE_URL}/email/update_email_risk",
                        json={
                            "email_id": email_id,
                            "is_block": is_block,  # 1=已拦截
                            "is_alert": is_alert   # 1=已告警 或 0=未告警（未配置邮箱）
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=5
                    )
                    
                    if update_resp.status_code == 200:
                        logger.info(f"✅ 拦截/告警状态已更新: is_block={is_block}, is_alert={is_alert}")
                    else:
                        logger.warning(f"⚠️ 更新拦截/告警状态失败: {update_resp.status_code}")
                except Exception as e:
                    logger.error(f"❌ 更新拦截/告警状态异常: {e}")
                
                return ai_result
                

            # ========== 不拦截则执行转发 ==========
            # 修改邮件主题（标记风险）
            DetectionEngine.modify_email_subject(message, ai_result)

            # 转发邮件
            forward_success = DetectionEngine.forward_email(message, email_id)

            if not forward_success:
                logger.error(f"❌ 邮件转发失败: {email_id}")
            
            # 即使转发成功，如果告警开启且有通知邮箱，也发送告警
            if alert_enabled and notification_email and risk_level > 0:
                logger.info(f"📧 邮件已转发，同时发送告警通知: {email_id}")
                send_alert_notification(
                    email_id=email_id,
                    risk_level=risk_level,
                    sender_email=parsed_sender,
                    subject=parsed_subject,
                    reason=ai_analysis.get("reason", "未知原因"),
                    notify_email=notification_email
                )
                is_alert = True  # 标记为已告警
                # ========== 更新告警状态到数据库（未拦截但告警） ==========
                try:
                    update_resp = requests.post(
                        f"{API_BASE_URL}/email/update_email_risk",
                        json={
                            "email_id": email_id,
                            "is_block": False,  # 未拦截（已转发）
                            "is_alert": True    # 已告警
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=5
                    )
                    
                    if update_resp.status_code == 200:
                        logger.info(f"✅ 告警状态已更新: is_alert=True")
                    else:
                        logger.warning(f"⚠️ 更新告警状态失败: {update_resp.status_code}")
                except Exception as e:
                    logger.error(f"❌ 更新告警状态异常: {e}")

        except Exception as e:
            logger.error(f"❌ 检测流程异常: {e}", exc_info=True)
            return 0

# 保存原始 run_detection 用于内部调用，避免无限递归
DetectionEngine.run_detection_orig = DetectionEngine.run_detection

# ==================== Celery任务 ====================
@celery_app.task(name="tasks.process_email_task", bind=True, max_retries=3)
def process_email_task(self, email_id, message_bytes, client_ip):
    try:
        logger.info(f"🚀 Celery任务开始: {email_id}, IP: {client_ip}")
        message = email.message_from_bytes(message_bytes)
        result = DetectionEngine.run_detection(email_id, message, client_ip)
        logger.info(f"✅ Celery任务完成: {email_id}, 结果: {result}")
        return result
    except Exception as e:
        logger.error(f"❌ Celery任务异常: {email_id}, 错误: {e}", exc_info=True)
        try:
            raise self.retry(exc=e, countdown=5)
        except self.MaxRetriesExceededError:
            logger.error(f"Celery任务重试次数已达上限: {email_id}")
            return 0