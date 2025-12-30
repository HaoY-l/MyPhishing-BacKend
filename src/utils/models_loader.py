import os
from sentence_transformers import SentenceTransformer
import chromadb
from src.utils.logger import logger

class ModelManager:
    _embedding_model = None
    _chroma_client = None

    @classmethod
    def get_embedding_model(cls):
        if cls._embedding_model is None:
            logger.info("🚀 正在加载 Embedding 模型...")
            # 这里的 project_root 需要根据你的实际目录结构调整
            model_path = os.path.join(os.getcwd(), "data", "bge-small")
            cls._embedding_model = SentenceTransformer(model_path)
            logger.info("✅ Embedding 模型加载成功")
        return cls._embedding_model

    @classmethod
    def get_chroma_client(cls):
        if cls._chroma_client is None:
            logger.info("🚀 正在初始化 Chroma 客户端...")
            chroma_path = os.path.join(os.getcwd(), "chroma_db")
            os.makedirs(chroma_path, exist_ok=True)
            cls._chroma_client = chromadb.PersistentClient(path=chroma_path)
            logger.info("✅ Chroma 客户端初始化成功")
        return cls._chroma_client

# 预加载函数供 app.py 调用
def init_all_models():
    ModelManager.get_embedding_model()
    ModelManager.get_chroma_client()