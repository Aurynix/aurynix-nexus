from fastapi import APIRouter

from app.api.v1 import auth, chat, documents, health, memory, oauth

router = APIRouter(prefix="/api/v1")

router.include_router(health.router)
router.include_router(auth.router)
router.include_router(chat.router)
router.include_router(documents.router)
router.include_router(memory.router)
router.include_router(oauth.router)
