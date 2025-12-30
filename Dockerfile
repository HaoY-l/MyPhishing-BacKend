# ==============================
# Builder 阶段
# ==============================
FROM python:3.12-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ make \
    wget ca-certificates \
    # SQLite 编译依赖
    autoconf libtool pkg-config \
    # Python 依赖编译所需
    libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# ==============================
# 编译安装 SQLite
# ==============================
RUN wget https://www.sqlite.org/2024/sqlite-autoconf-3450000.tar.gz && \
    tar -xzf sqlite-autoconf-3450000.tar.gz && \
    cd sqlite-autoconf-3450000 && \
    ./configure --prefix=/usr/local --disable-dependency-tracking --disable-static && \
    make -j$(nproc) && make install && \
    cd .. && rm -rf sqlite-autoconf-3450000*

# ==============================
# 创建虚拟环境并安装依赖
# ==============================
COPY requirements.txt .

RUN python -m venv /opt/venv && \
    . /opt/venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip setuptools wheel && \
    LD_LIBRARY_PATH=/usr/local/lib pip install --no-cache-dir \
        --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
        --extra-index-url https://pypi.org/simple \
        -r requirements.txt

# 清理虚拟环境
RUN . /opt/venv/bin/activate && \
    find /opt/venv -type f -name "*.pyc" -delete && \
    find /opt/venv -type f -name "*.pyo" -delete && \
    find /opt/venv -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -type d -name "test" -exec rm -rf {} + 2>/dev/null || true && \
    rm -rf /opt/venv/lib/python3.12/site-packages/pip* \
           /opt/venv/lib/python3.12/site-packages/setuptools*

# ==============================
# Runtime 阶段
# ==============================
FROM python:3.12-slim

WORKDIR /app

# 只安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 wget ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ==============================
# 从 Builder 拷贝产物
# ==============================
COPY --from=builder /usr/local/bin/sqlite3 /usr/local/bin/sqlite3
COPY --from=builder /usr/local/lib/libsqlite3.so.* /usr/local/lib/
COPY --from=builder /opt/venv /opt/venv

# 更新动态链接库
RUN echo "/usr/local/lib" > /etc/ld.so.conf.d/sqlite3.conf && ldconfig

# ==============================
# 拷贝应用代码
# ==============================
COPY . .
RUN chmod +x start.sh

# ==============================
# 环境变量
# ==============================
ENV PATH="/opt/venv/bin:$PATH" \
    LD_LIBRARY_PATH="/usr/local/lib:$LD_LIBRARY_PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000 25

CMD ["./start.sh"]