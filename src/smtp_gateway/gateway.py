import os, aiohttp, email, json, re, uuid, asyncio, time, socket, sys
from aiosmtpd.controller import Controller
from aiosmtpd.handlers import AsyncMessage
from email.utils import getaddresses, parseaddr, parsedate_to_datetime
from email.header import decode_header
from datetime import datetime
from src.utils.logger import logger
from collections import defaultdict
from tasks import process_email_task  # 导入 Celery 任务

SAVE_EMAIL_API_URL = "http://localhost:8000/api/email/save_email"

# ========== 新增：通用邮件头解析工具 ==========
def decode_mime_header(value: str) -> str:
    """解码MIME编码的邮件头（如中文名称）"""
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

def parse_email_addresses(header_values):
    """
    解析邮件地址列表，支持MIME编码、多格式分隔符
    返回：纯邮箱地址列表（小写）
    """
    if not header_values:
        return []
    
    # 拼接所有header值，交给getaddresses处理（Python内置的专业解析工具）
    full_address_str = ', '.join(header_values)
    addr_tuples = getaddresses([full_address_str])
    
    # 提取纯邮箱地址并去重
    email_list = []
    for _, email_addr in addr_tuples:
        if email_addr:
            email_addr = email_addr.lower().strip()
            # 简单的邮箱格式校验
            if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email_addr):
                email_list.append(email_addr)
    
    # 去重并保持顺序
    return list(dict.fromkeys(email_list))

def get_pure_sender_email(message):
    """从邮件中提取纯发件人邮箱（无昵称）"""
    from_header = message.get('From', '')
    if not from_header:
        return ""
    # 解析发件人：(昵称, 邮箱)
    _, sender_email = parseaddr(from_header)
    return sender_email.lower().strip() if sender_email else ""

def get_email_send_time(message):
    """解析邮件发送时间，返回格式化字符串"""
    # 优先用邮件的Date头
    date_header = message.get('Date', '')
    if date_header:
        try:
            send_time = parsedate_to_datetime(date_header)
            return send_time.strftime('%Y-%m-%d %H:%M:%S')
        except Exception as e:
            logger.warning(f"解析Date头失败: {e}")
    # 兜底用当前时间
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

class AIGatewayHandler(AsyncMessage):
    _ip_limits = defaultdict(lambda: {"times": [], "blocked_until": 0})
    RATE_LIMIT_PER_MINUTE = int(os.getenv("GATEWAY_RATE_LIMIT", 50))
    BLOCK_DURATION = int(os.getenv("GATEWAY_BLOCK_DURATION", 600))

    def __init__(self):
        super().__init__()

    def _get_client_ip(self, message):
        peer_info = message.get('X-Peer', '')
        if peer_info:
            ip_match = re.search(r"\('([^']+)'", peer_info)
            if ip_match: return ip_match.group(1)
        received = message.get_all('Received', [])
        if received:
            ip_match = re.search(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', received[-1])
            if ip_match: return ip_match.group(0)
        return "127.0.0.1"

    async def save_email_to_api(self, email_data):
        """异步保存邮件初始存根到数据库"""
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(SAVE_EMAIL_API_URL, json=email_data, timeout=5) as resp:
                    if resp.status == 200:
                        resp_json = await resp.json()
                        return resp_json.get("email_id")
                logger.warning(f"保存邮件API返回异常: {resp.status}")
            except Exception as e:
                logger.error(f"保存邮件初始信息失败: {e}", exc_info=True)
            return None

    async def handle_message(self, message):
        try:
            client_ip = self._get_client_ip(message)

            # 1️⃣ 提取并校验收件人（修复核心）
            recipients_raw = message.get_all('To', [])
            my_domains = [
                d.strip().lower()
                for d in os.getenv("MY_EMAIL_DOMAINS", "").split(',')
                if d.strip()
            ]

            # 修复：使用专业工具解析收件人地址
            all_recipients = parse_email_addresses(recipients_raw)
            
            # 筛选属于自己域名的收件人
            recipients = []
            if my_domains:
                for addr in all_recipients:
                    if any(addr.endswith(f"@{domain}") for domain in my_domains):
                        recipients.append(addr)
            else:
                # 如果没有配置域名，接收所有合法收件人
                recipients = all_recipients

            # 去重，保持顺序
            recipients = list(dict.fromkeys(recipients))

            if not recipients:
                logger.warning(f"[安全拦截] 没有合法收件人: {recipients_raw} | 解析出的所有地址: {all_recipients}")
                return

            logger.info(f"📥 SMTP接收邮件，合法收件人数量: {len(recipients)} | 收件人列表: {recipients}")

            # 2️⃣ 解析公共数据（所有收件人共用）
            pure_sender = get_pure_sender_email(message)  # 纯邮箱地址
            send_time = get_email_send_time(message)      # 发送时间
            raw_subject = message.get('Subject', '')
            parsed_subject = decode_mime_header(raw_subject)  # 解码后的主题

            # 3️⃣ ⚠️ 核心：按「收件人」拆分
            for recipient in recipients:
                email_id = str(uuid.uuid4())

                email_data = {
                    "email_id": email_id,
                    "sender": pure_sender,               # ✅ 强制用纯邮箱
                    "recipient": recipient,              # ✅ 单个收件人
                    "subject": parsed_subject,           # ✅ 解码后的主题
                    "send_time": send_time,              # ✅ 发送时间
                    "client_ip": client_ip,
                    "content_text": "(Processing...)"
                }

                saved_email_id = await self.save_email_to_api(email_data)
                if not saved_email_id:
                    logger.error(f"❌ 保存失败，跳过该收件人: {recipient}")
                    continue

                # 4️⃣ 投递 Celery（一人一任务）
                process_email_task.delay(
                    email_id=saved_email_id,
                    message_bytes=message.as_bytes(),
                    client_ip=client_ip
                )

                logger.info(
                    f"📨 邮件已入队: email_id={saved_email_id}, recipient={recipient}, sender={pure_sender}"
                )

            # 5️⃣ 立刻返回 250 OK
            return

        except Exception as e:
            logger.error("❌ 网关处理异常", exc_info=True)

class SMTPGateway:
    def __init__(self, host=None, port=None):
        self.host = host or os.getenv("SMTP_LISTEN_HOST", "0.0.0.0")
        self.port = port or int(os.getenv("SMTP_LISTEN_PORT", 25))
        self.controller = None

    def start(self):
        # 1️⃣ 测试 bind 权限
        try:
            test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            test_sock.bind((self.host, self.port))
            test_sock.close()
        except PermissionError:
            logger.critical("💥 SMTP 25端口绑定失败，需要 root 或 CAP_NET_BIND_SERVICE")
            sys.exit(1)
        except OSError as e:
            logger.critical(f"💥 端口 {self.port} 被占用: {e}")
            sys.exit(1)

        # 2️⃣ 启动真正的 Controller
        self.controller = Controller(AIGatewayHandler(), hostname=self.host, port=self.port)
        self.controller.start()

        # 3️⃣ 确认监听
        time.sleep(0.5)
        import subprocess
        out = subprocess.getoutput(f"netstat -nltp | grep ':{self.port} '")
        if not out:
            logger.critical(f"💥 SMTP 网关启动失败，端口 {self.port} 未监听")
            sys.exit(1)

        logger.info(f"📡 SMTP 网关已成功监听 {self.host}:{self.port}")

        # 4️⃣ 阻塞主线程
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        if self.controller:
            self.controller.stop()
            logger.info("🛑 SMTP 网关已停止")