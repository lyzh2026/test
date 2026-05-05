FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

# ========== 配置 Ubuntu 国内源（清华镜像）==========
RUN sed -i 's/archive.ubuntu.com/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list && \
    sed -i 's/security.ubuntu.com/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list
# ================================================

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 配置 pip 国内源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 复制并安装 Python 依赖
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# 复制应用代码
COPY . /app

# 创建静态目录
RUN mkdir -p /app/static/render_failures

# 入口
CMD ["bash", "-lc", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
