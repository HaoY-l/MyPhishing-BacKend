import os, sys, time
from dotenv import load_dotenv

load_dotenv()

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.smtp_gateway.gateway import SMTPGateway
from src.utils.logger import logger

def main():
    logger.info("🚀 启动 SMTP 网关...")
    gateway = SMTPGateway()

    try:
        gateway.start()  # 阻塞
    except KeyboardInterrupt:
        logger.info("🛑 SMTP 网关关闭中...")
        gateway.stop()

if __name__ == "__main__":
    main()
