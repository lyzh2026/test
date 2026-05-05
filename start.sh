#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

MODE="${1:-full}"

echo -e "${CYAN}╔══════════════════════════════════════════╗"
echo -e "║     拾讯 (Shixun) - 本地开发启动器    ║"
echo -e "╚══════════════════════════════════════════╝${NC}"

case "$MODE" in
  full)    echo -e "${YELLOW}[模式] 完整启动 (DB容器 + 前后端)${NC}" ;;
  app)     echo -e "${YELLOW}[模式] 仅启动前后端 (需自备 PostgreSQL + Redis)${NC}" ;;
  db)      echo -e "${YELLOW}[模式] 仅启动数据库容器${NC}" ;;
  install) echo -e "${YELLOW}[模式] 仅安装依赖${NC}" ;;
  help|--help|-h)
    echo "用法: ./start.sh [full|app|db|install|help]"
    echo "  full    完整启动（默认）"
    echo "  app     仅前后端（需自备 PostgreSQL + Redis）"
    echo "  db      仅数据库容器（PostgreSQL + Redis）"
    echo "  install 仅安装依赖"
    exit 0
    ;;
  *)
    echo -e "${RED}用法: ./start.sh [full|app|db|install|help]${NC}"
    exit 1
    ;;
esac

# ─── 1. 基础环境检查 ─────────────────────────────────
echo ""
echo -e "${CYAN}>>> 检查运行环境...${NC}"

command -v python3 >/dev/null 2>&1 && PY=python3 || { command -v python >/dev/null 2>&1 && PY=python; }
if [ -z "${PY:-}" ]; then
  echo -e "${RED}[错误] 未找到 Python，请安装 Python 3.10+${NC}"
  exit 1
fi
$PY -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null || {
  echo -e "${RED}[错误] Python 版本过低，需要 3.10+${NC}"
  exit 1
}

command -v node >/dev/null 2>&1 || {
  echo -e "${RED}[错误] 未找到 Node.js，请安装 Node.js 18+${NC}"
  exit 1
}

echo -e " ${GREEN}✓${NC} $($PY --version 2>&1)"
echo -e " ${GREEN}✓${NC} Node $(node -v)"

# ─── 2. .env ─────────────────────────────────────────
echo ""
echo -e "${CYAN}>>> 检查 .env 文件...${NC}"
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    echo -e " ${YELLOW}⚠  已从 .env.example 创建 .env"
    echo -e " ⚠  请检查 .env 中的配置，至少填入: ADMIN_PASSWORD, SESSION_SECRET, MOONSHOT_API_KEY${NC}"
    echo -e " ${YELLOW}⚠  直接启动模式下 REDIS_HOST 需改为 localhost${NC}"
  else
    echo -e "${RED}[错误] .env.example 不存在${NC}"
    exit 1
  fi
else
  echo -e " ${GREEN}✓${NC} .env 已存在"
fi

# ─── 3. 启动数据库 ───────────────────────────────────
start_db() {
  echo ""
  echo -e "${CYAN}>>> 启动 PostgreSQL + Redis 容器...${NC}"
  docker compose up -d postgres redis 2>&1 | grep -v Network || true
  echo -e " ${GREEN}✓${NC} 数据库容器已启动"

  echo -e "${CYAN}>>> 等待数据库就绪...${NC}"
  until docker compose exec postgres pg_isready -U shixun -d shixun >/dev/null 2>&1; do
    sleep 2
  done
  echo -e " ${GREEN}✓${NC} PostgreSQL 就绪"
}

case "$MODE" in
  full)
    echo ""
    echo -e "${CYAN}>>> 检查 Docker...${NC}"
    command -v docker >/dev/null 2>&1 || {
      echo -e "${RED}[错误] 未找到 Docker${NC}"
      exit 1
    }
    echo -e " ${GREEN}✓${NC} Docker 可用"
    start_db

    # 数据库容器在 Docker 中，后端直接运行时需要通过 localhost 连接
    export DATABASE_URL="postgresql+asyncpg://shixun:shixun@localhost:5432/shixun"
    export DATABASE_URL_SYNC="postgresql+psycopg2://shixun:shixun@localhost:5432/shixun"
    export REDIS_HOST="localhost"
    ;;
  db)
    command -v docker >/dev/null 2>&1 || { echo -e "${RED}[错误] 未找到 Docker${NC}"; exit 1; }
    start_db
    exit 0
    ;;
esac

# ─── 4. 后端依赖 ─────────────────────────────────────
echo ""
echo -e "${CYAN}>>> 配置 Python 虚拟环境...${NC}"
if [ ! -d backend/.venv ]; then
  $PY -m venv backend/.venv
  echo -e " ${GREEN}✓${NC} 虚拟环境已创建"
else
  echo -e " ${GREEN}✓${NC} 虚拟环境已存在"
fi

echo -e "${CYAN}>>> 安装后端 Python 依赖...${NC}"
backend/.venv/bin/pip install -r backend/requirements.txt -q
echo -e " ${GREEN}✓${NC} Python 依赖已安装"

# ─── 5. 前端依赖 ─────────────────────────────────────
echo ""
echo -e "${CYAN}>>> 安装前端 Node 依赖...${NC}"
if [ ! -d frontend/node_modules ]; then
  (cd frontend && npm install --no-audit --no-fund)
fi
echo -e " ${GREEN}✓${NC} 前端依赖已准备"

if [ "$MODE" = "install" ]; then
  echo -e "\n${GREEN}✅ 依赖安装完成${NC}"
  exit 0
fi

# ─── 6. 数据库迁移 ───────────────────────────────────
echo ""
echo -e "${CYAN}>>> 运行数据库迁移...${NC}"
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head 2>/dev/null || {
  echo -e "${RED}[警告] 数据库迁移失败，请检查数据库连接${NC}"
  echo "   确认 .env 中 DATABASE_URL 配置正确"
  echo "   直接启动模式应使用: DATABASE_URL=postgresql+asyncpg://shixun:shixun@localhost:5432/shixun"
  exit 1
}
echo -e " ${GREEN}✓${NC} 数据库迁移完成"

# ─── 7. 启动服务 ─────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗"
echo -e "║      启动服务...                       ║"
echo -e "╚══════════════════════════════════════════╝${NC}"

# 清理函数
cleanup() {
  echo -e "\n${YELLOW}正在关闭服务...${NC}"
  kill $BACKEND_PID 2>/dev/null || true
  exit 0
}
trap cleanup SIGINT SIGTERM EXIT

echo -e "${YELLOW}[后端] 启动 FastAPI (uvicorn)...${NC}"
backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend &
BACKEND_PID=$!

echo -e "${YELLOW}[前端] 启动 Next.js...${NC}"
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗"
echo -e "║  前端: http://localhost:3000           ║"
echo -e "║  后端: http://localhost:8000           ║"
echo -e "║  API 文档: http://localhost:8000/docs  ║"
echo -e "║                                      ║"
echo -e "║  按 Ctrl+C 停止所有服务               ║"
echo -e "╚══════════════════════════════════════════╝${NC}"
echo ""

(cd frontend && npm run dev)
