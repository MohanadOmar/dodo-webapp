"""
/knowledge/upload — accepts file uploads from the client portal,
chunks the text, embeds it via OpenAI, stores in Supabase documents table.
"""
import os
import io
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from tools import get_openai, upload_document_chunks, list_client_documents, delete_client_document

router = APIRouter()

CHUNK_SIZE = 500      # characters per chunk
CHUNK_OVERLAP = 50    # overlap between chunks


def _chunk_text(text: str) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunks.append(text[start:end].strip())
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c]


def _extract_text(filename: str, content: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "txt":
        return content.decode("utf-8", errors="ignore")
    if ext == "pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            raise HTTPException(500, "pypdf not installed. Add pypdf to requirements.txt")
    raise HTTPException(400, f"Unsupported file type: .{ext}. Use .txt or .pdf")


def _check_auth(request: Request):
    expected = os.environ.get("CHAT_API_KEY", "")
    if not expected:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != expected:
        raise HTTPException(401, "Unauthorized")


@router.post("/upload")
async def upload_knowledge(
    request: Request,
    file: UploadFile = File(...),
    user_id: str = Form(...),
):
    _check_auth(request)

    if not user_id:
        raise HTTPException(400, "user_id is required")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(400, "File too large. Max 10MB.")

    # Extract text
    text = _extract_text(file.filename, content)
    if not text.strip():
        raise HTTPException(400, "Could not extract text from file.")

    # Chunk
    chunks = _chunk_text(text)
    if not chunks:
        raise HTTPException(400, "No content found in file.")

    # Embed all chunks
    client = get_openai()
    embeddings_res = client.embeddings.create(
        model="text-embedding-3-small",
        input=chunks,
    )
    embedded_chunks = [
        {"content": chunk, "embedding": embeddings_res.data[i].embedding}
        for i, chunk in enumerate(chunks)
    ]

    # Store
    result = upload_document_chunks(
        chunks=embedded_chunks,
        user_id=user_id,
        source_name=file.filename,
    )

    return {
        "success": True,
        "file": file.filename,
        "chunks_uploaded": result["uploaded"],
    }


@router.get("/list")
async def list_documents(request: Request, user_id: str):
    _check_auth(request)
    if not user_id:
        raise HTTPException(400, "user_id is required")
    docs = list_client_documents(user_id)
    return {"documents": docs}


@router.delete("/delete")
async def delete_document(request: Request, user_id: str, source_name: str):
    _check_auth(request)
    if not user_id:
        raise HTTPException(400, "user_id is required")
    result = delete_client_document(source_name=source_name, user_id=user_id)
    return {"success": True, "deleted": result["deleted"]}
