from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, UploadFile, File

router = APIRouter(prefix="/admin/poi", tags=["poi-admin"])

UPLOAD_DIR = Path("src/data/poi/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def build_poi_admin_router(poi_admin_service):
    @router.post("/import")
    async def import_poi(file: UploadFile = File(...)):
        save_path = UPLOAD_DIR / file.filename
        content = await file.read()
        save_path.write_bytes(content)

        result = poi_admin_service.import_poi_file(str(save_path))
        return result

    return router
