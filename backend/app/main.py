from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.devices import router as devices_router
from .api.health import router as health_router
from .api.install import router as install_router
from .api.logs import router as logs_router
from .api.mirror import router as mirror_router
from .api.mirror import shutdown_all_drivers
from .core.alias_manager import alias_manager
from .core.device_manager import device_manager
from .core.log_buffer import setup_logging
from .websocket.control import router as ws_control_router
from .websocket.devices import router as ws_devices_router
from .websocket.handler import router as ws_router
from .websocket.video import router as ws_video_router

# 模块导入时即配置日志，确保 uvicorn 直接加载 app.main:app 时同样生效
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    import os
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alias_manager.init(backend_root)
    device_manager.start()
    await device_manager.refresh()
    yield
    await shutdown_all_drivers()
    await device_manager.stop_async()
    # 共享 tunnel agent 不随设备级清理终止，应用关闭时统一收尾，避免 ios.exe 残留
    from .drivers.adapters.goios_adapter import shutdown_tunnel_agents
    await asyncio.to_thread(shutdown_tunnel_agents)


app = FastAPI(title="MSCA Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(logs_router, prefix="/api")
app.include_router(devices_router, prefix="/api")
app.include_router(mirror_router, prefix="/api")
app.include_router(install_router, prefix="/api")
app.include_router(ws_router)
app.include_router(ws_devices_router)
app.include_router(ws_video_router)
app.include_router(ws_control_router)
