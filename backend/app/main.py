from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.devices import router as devices_router
from app.api.health import router as health_router
from app.api.mirror import router as mirror_router
from app.core.device_manager import device_manager
from app.websocket.devices import router as ws_devices_router
from app.websocket.handler import router as ws_router
from app.websocket.video import router as ws_video_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    device_manager.start()
    await device_manager.refresh()
    yield
    device_manager.stop()


app = FastAPI(title="MSCA Backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(devices_router, prefix="/api")
app.include_router(mirror_router, prefix="/api")
app.include_router(ws_router)
app.include_router(ws_devices_router)
app.include_router(ws_video_router)
