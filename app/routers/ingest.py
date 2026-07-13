
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, HttpUrl

from app.core.state import state

router = APIRouter(prefix="/ingest", tags=["ingest"])

@router.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    if not state.ingest_service:
        raise HTTPException(status_code=503, detail="IngestService not initialized")
    
    results = []
    for file in files:
        try:
            result = await state.ingest_service.ingest_file(file)
            results.append(result)
        except Exception as e:
            results.append({"name": file.filename, "status": "error", "error": str(e)})
            
    return results

class UrlIngestRequest(BaseModel):
    url: HttpUrl

@router.post("/url")
async def ingest_url(request: UrlIngestRequest):
    if not state.ingest_service:
        raise HTTPException(status_code=503, detail="IngestService not initialized")
    try:
        result = await state.ingest_service.ingest_url(str(request.url))
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = state.job_registry.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.get("/documents")
async def list_documents():
    if not state.ingest_service:
        raise HTTPException(status_code=503, detail="IngestService not initialized")
    return await state.ingest_service.get_documents()

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    if not state.ingest_service:
        raise HTTPException(status_code=503, detail="IngestService not initialized")
    success = await state.ingest_service.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete document")
    return {"status": "success", "doc_id": doc_id}

@router.put("/documents/{doc_id}")
async def replace_document(doc_id: str, file: UploadFile = File(...)):
    if not state.ingest_service:
        raise HTTPException(status_code=503, detail="IngestService not initialized")
        
    success = await state.ingest_service.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete old document chunks")
        
    try:
        result = await state.ingest_service.ingest_file(file, doc_id=doc_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
