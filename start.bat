@echo off
chcp 65001 >nul
title 拾讯 - 本地开发启动器
setlocal enabledelayedexpansion

:: ──────────────── 颜色 ────────────────
set ESC=
set GREEN=%ESC%[32m
set YELLOW=%ESC%[33m
set RED=%ESC%[31m
set CYAN=%ESC%[36m
set NC=%ESC%[0m

echo %CYAN%╔══════════════════════════════════════════╗
echo ║     拾讯 (Shixun) - 本地开发启动器    ║
echo ╚══════════════════════════════════════════╝%NC%

:: ──────────────── 模式选择 ────────────────
set MODE=%1
if "%MODE%"=="" set MODE=full

if "%MODE%"=="full" (
    echo %YELLOW%[模式] 完整启动 ^(DB容器 + 前后端%NC%)
) else if "%MODE%"=="app" (
    echo %YELLOW%[模式] 仅启动前后端 ^(需自备 PostgreSQL + Redis%NC%)
) else if "%MODE%"=="db" (
    echo %YELLOW%[模式] 仅启动数据库容器%NC%)
) else if "%MODE%"=="install" (
    echo %YELLOW%[模式] 仅安装依赖%NC%)
) else (
    echo %RED%用法: start.bat [full^|app^|db^|install^|help]%NC%
    echo    full    完整启动（默认）
    echo    app     仅前后端（需自备 PostgreSQL + Redis）
    echo    db      仅数据库容器（PostgreSQL + Redis）
    echo    install 仅安装依赖
    goto :eof
)

:: ──────────────── 1. 检查基础环境 ────────────────
echo.
echo %CYAN%>>> 检查运行环境...%NC%

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[错误] 未找到 Python，请安装 Python 3.10+%NC%
    pause
    exit /b 1
)

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[错误] 未找到 Node.js，请安装 Node.js 18+%NC%
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('node -v') do set NODE_VER=%%i
for /f "tokens=*" %%i in ('python -V') do set PYTHON_VER=%%i
echo  %GREEN%✓%NC% %PYTHON_VER%
echo  %GREEN%✓%NC% Node %NODE_VER%

:: ──────────────── 2. 准备 .env ────────────────
echo.
echo %CYAN%>>> 检查 .env 文件...%NC%
if not exist ".env" (
    if exist ".env.example" (
        echo   .env 不存在，从 .env.example 复制...
        copy .env.example .env >nul
        echo %YELLOW%  ⚠ 请检查 .env 中的配置，至少填入: ADMIN_PASSWORD, SESSION_SECRET, MOONSHOT_API_KEY%NC%
        echo %YELLOW%  ⚠ 直接启动模式下 REDIS_HOST 需改为 localhost%NC%
    ) else (
        echo %RED%[错误] .env.example 不存在，无法创建配置%NC%
        pause
        exit /b 1
    )
) else (
    echo   %GREEN%✓%NC% .env 已存在
)

:: ──────────────── 3. 启动数据库容器 ────────────────
if "%MODE%"=="full" (
    echo.
    echo %CYAN%>>> 检查 Docker...%NC%
    where docker >nul 2>&1
    if %errorlevel% neq 0 (
        echo %RED%[错误] 未找到 Docker，无法启动数据库容器%NC%
        echo   请安装 Docker，或使用 start.bat app 模式（自备数据库）
        pause
        exit /b 1
    )
    echo   %GREEN%✓%NC% Docker 可用

    echo %CYAN%>>> 启动 PostgreSQL + Redis 容器...%NC%
    docker compose up -d postgres redis 2>&1 | findstr /V "Network"
    if !errorlevel! neq 0 (
        echo %RED%[错误] 数据库容器启动失败%NC%
        pause
        exit /b 1
    )
    echo   %GREEN%✓%NC% 数据库容器已启动

    echo %CYAN%>>> 等待数据库就绪...%NC%
    :wait_db
    docker compose exec postgres pg_isready -U shixun -d shixun >nul 2>&1
    if !errorlevel! neq 0 (
        timeout /t 2 /nobreak >nul
        goto wait_db
    )
    echo   %GREEN%✓%NC% PostgreSQL 就绪

    :: 数据库容器在 Docker 中，后端直接运行时需要通过 localhost 连接
    set DATABASE_URL=postgresql+asyncpg://shixun:shixun@localhost:5432/shixun
    set DATABASE_URL_SYNC=postgresql+psycopg2://shixun:shixun@localhost:5432/shixun
    set REDIS_HOST=localhost
)

if "%MODE%"=="db" (
    echo %CYAN%>>> 检查 Docker...%NC%
    where docker >nul 2>&1
    if %errorlevel% neq 0 (
        echo %RED%[错误] 未找到 Docker%NC%
        pause
        exit /b 1
    )
    docker compose up -d postgres redis 2>&1 | findstr /V "Network"
    echo   %GREEN%✓%NC% 数据库容器已启动
    exit /b 0
)

:: ──────────────── 4. 安装后端依赖 ────────────────
echo.
echo %CYAN%>>> 配置 Python 虚拟环境...%NC%
if not exist "backend\.venv" (
    python -m venv backend\.venv
    echo   %GREEN%✓%NC% 虚拟环境已创建
) else (
    echo   %GREEN%✓%NC% 虚拟环境已存在
)

echo %CYAN%>>> 安装后端 Python 依赖...%NC%
call backend\.venv\Scripts\pip install -r backend\requirements.txt >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[错误] Python 依赖安装失败%NC%
    pause
    exit /b 1
)
echo   %GREEN%✓%NC% Python 依赖已安装

:: ──────────────── 5. 安装前端依赖 ────────────────
echo.
echo %CYAN%>>> 安装前端 Node 依赖...%NC%
cd frontend
if not exist "node_modules" (
    call npm install --no-audit --no-fund 2>&1
    if !errorlevel! neq 0 (
        echo %RED%[错误] 前端依赖安装失败%NC%
        cd ..
        pause
        exit /b 1
    )
) else (
    echo   %GREEN%✓%NC% node_modules 已存在
)
cd ..
echo   %GREEN%✓%NC% 前端依赖已准备

if "%MODE%"=="install" (
    echo.
    echo %GREEN%✅ 依赖安装完成%NC%
    exit /b 0
)

:: ──────────────── 6. 数据库迁移 ────────────────
echo.
echo %CYAN%>>> 运行数据库迁移...%NC%
call backend\.venv\Scripts\alembic -c backend\alembic.ini upgrade head >nul 2>&1
if %errorlevel% neq 0 (
    echo %RED%[警告] 数据库迁移失败，请检查数据库连接%NC%
    echo   确认 .env 中 DATABASE_URL 配置正确
    echo   直接启动模式应使用: DATABASE_URL=postgresql+asyncpg://shixun:shixun@localhost:5432/shixun
    pause
    exit /b 1
)
echo   %GREEN%✓%NC% 数据库迁移完成

:: ──────────────── 7. 启动服务 ────────────────
echo.
echo %CYAN%╔══════════════════════════════════════════╗
echo ║      启动服务...                       ║
echo ╚══════════════════════════════════════════╝%NC%

:: 后端 - 新窗口运行
echo %YELLOW%[后端] 启动 FastAPI (uvicorn)...%NC%
start "拾讯-后端" cmd /c "title 拾讯-后端 & call backend\.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --app-dir backend"

echo %YELLOW%[前端] 启动 Next.js...%NC%
echo.
echo %GREEN%╔══════════════════════════════════════════╗
echo ║  前端: http://localhost:3000           ║
echo ║  后端: http://localhost:8000           ║
echo ║  API 文档: http://localhost:8000/docs  ║
echo ║                                      ║
echo ║  按 Ctrl+C 关闭前端                    ║
echo ╚══════════════════════════════════════════╝%NC%
echo.

cd frontend
call npm run dev
cd ..

echo.
echo %RED%前端已关闭，正在清理...%NC%
exit /b 0
