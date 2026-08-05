from fastapi import APIRouter

from app.api.routes import auth, files, focus, plans, questions, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(plans.router)
api_router.include_router(questions.router)
api_router.include_router(questions.wrong_book_router)
api_router.include_router(files.router)
api_router.include_router(focus.router)
api_router.include_router(focus.pet_router)
api_router.include_router(focus.coin_router)
