"""FastAPI 应用入口"""

import os
import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import api_router
from app.services.chat_generation_service import chat_generations
# 启动时触发 Tool Registry 注册（副作用 import）
import app.agents.tools.meeting_ops  # noqa: F401

# 配置 app logger（uvicorn 默认 root level=WARNING，需显式设置 INFO）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logging.getLogger("app").setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动与关闭"""
    # 启动时
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    try:
        yield
    finally:
        await chat_generations.aclose()
        # 关闭时：关闭 SFU 连接池等资源
        from app.services.sfu_bridge import sfu_bridge
        await sfu_bridge.aclose()


app = FastAPI(
    title=settings.APP_NAME,
    description="研发会议垂类 Agent 平台 API（评审决策 / 对齐闭环 / 复盘闭环）",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router)


@app.get("/")
async def root():
    """根路径"""
    return {"message": settings.APP_NAME, "docs": "/docs"}
