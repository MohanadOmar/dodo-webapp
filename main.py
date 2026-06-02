import os
from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
import uvicorn

from sms import router as sms_router
from n8n_webhook import router as n8n_router
from retell_ws import router as retell_router
from web_chat import router as chat_router
from gmail_poller import start_poller
from reminder_poller import start_reminder_poller


@asynccontextmanager
async def lifespan(app: FastAPI):
    gmail_task = asyncio.create_task(start_poller())
    reminder_task = asyncio.create_task(start_reminder_poller())
    yield
    gmail_task.cancel()
    reminder_task.cancel()


app = FastAPI(lifespan=lifespan)

# CORS — allow eg23.net frontend to call the API
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://eg23.net",
        "https://www.eg23.net",
        "http://localhost:3000",  # local dev
        "http://localhost:5173",  # vite dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sms_router, prefix="/sms")
app.include_router(n8n_router, prefix="/n8n")
app.include_router(retell_router)
app.include_router(chat_router, prefix="/chat")


@app.get("/health")
def health():
    return {"status": "Dodo is alive 🦤"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
