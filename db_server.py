import os, sys
from dotenv import load_dotenv

load_dotenv()

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.utils.logger import logger
from data.db_init import create_database_and_tables
from src.utils.models_loader import init_all_models

def main():
    logger.info("🚀 系统初始化开始")

    # 1️⃣ 数据库
    create_database_and_tables()
    logger.info("✅ 数据库初始化完成")

    # 2️⃣ 模型（只在这里加载一次）
    init_all_models()
    logger.info("✅ 模型加载完成")

    logger.info("🎉 系统初始化完成")

if __name__ == "__main__":
    main()
