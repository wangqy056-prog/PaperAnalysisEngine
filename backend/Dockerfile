# Paper Analysis Engine - Backend Dockerfile
# 基于 Python 3.11 slim（Debian），轻量且安全

FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app/backend

# 安装系统依赖（Playwright 需要 chromium + matplotlib 需要中文字体）
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    unzip \
    ca-certificates \
    fonts-wqy-zenhei \
    fonts-noto-color-emoji \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0 \
    libgtk-3-0 \
    libnspr4 \
    libpango-1.0-0 \
    libx11-xcb1 \
    libxcb-dri3-0 \
    libxcomposite1 \
    libxcursor1 \
    libxfixes3 \
    libxi6 \
    libxrandr2 \
    libxrender1 \
    libxshmfence1 \
    libxtst6 \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    requests \
    networkx \
    matplotlib \
    numpy \
    python-dotenv \
    curl-cffi \
    playwright \
    && playwright install chromium --with-deps

# 复制后端代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8001

# 启动命令（读取 .env 环境变量）
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
