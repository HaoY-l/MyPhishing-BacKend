import os,sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import chromadb
import logging
from dotenv import load_dotenv
from chromadb.config import Settings

# ===================== 基础配置 =====================
# 加载.env环境变量
load_dotenv()


# ===================== Chroma 核心初始化 =====================
def init_chroma():
    """
    仅初始化Chroma客户端和集合（无数据导入）
    - 创建持久化客户端（数据存储到本地文件夹）
    - 创建/获取指定的collection
    - 返回初始化后的客户端和集合对象
    """
    try:
        # 1. 初始化Chroma持久化客户端（指定存储路径）
        # path参数：向量数据会持久化到当前目录的chroma_phishing_db文件夹
        chroma_client = chromadb.PersistentClient(
            path="./chroma_phishing_db",
            settings=Settings(
                anonymized_telemetry=False,  # 关闭匿名数据上报
                allow_reset=True  # 允许重置集合（可选，根据需要）
            )
        )
        logger.info("✅ Chroma客户端初始化成功")

        # 2. 创建/获取集合（如果已存在则获取，不存在则创建）
        collection = chroma_client.get_or_create_collection(
            name="email_embeddings",
            metadata={"description": "Phishing email content embeddings"},
            # 可选：指定距离函数（默认cosine，适合文本向量）
            embedding_function=None  # 向量由外部接口生成，这里暂不指定
        )
        logger.info(f"✅ Chroma集合「email_embeddings」初始化成功（当前集合数据量：{collection.count()}）")

        return chroma_client, collection

    except Exception as e:
        logger.error(f"❌ Chroma初始化失败：{str(e)}", exc_info=True)
        raise  # 抛出异常，方便感知初始化失败

# ===================== 主执行逻辑（仅初始化） =====================
if __name__ == "__main__":
    # 仅执行Chroma初始化，无任何数据导入操作
    try:
        # 执行初始化
        chroma_client, collection = init_chroma()
        logger.info("🎉 Chroma初始化流程全部完成！")
        logger.info(f"提示：集合存储路径 -> {os.path.abspath('./chroma_phishing_db')}")
        logger.info("后续可通过 chroma_client/collection 对象编写数据导入逻辑")
    except Exception as e:
        logger.critical("💥 初始化失败，程序退出", exc_info=True)
        exit(1)