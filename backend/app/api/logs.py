"""后端运行日志查询 API。"""

from fastapi import APIRouter, Query

from ..core.log_buffer import get_log_file_path, get_recent_logs

router = APIRouter()

MAX_QUERY_LINES = 2000


@router.get("/logs")
async def get_logs(lines: int = Query(default=500, ge=1, le=MAX_QUERY_LINES)):
    entries = get_recent_logs(lines)
    return {
        "lines": entries,
        "total": len(entries),
        "log_file": get_log_file_path(),
    }
