from fastapi import APIRouter

from app.api.routes import (
    auth,
    files,
    focus,
    onboarding,
    ops,
    plan_chat,
    plans,
    questions,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(onboarding.router)
api_router.include_router(users.router)
api_router.include_router(plans.router)
api_router.include_router(plan_chat.router)
api_router.include_router(questions.router)
api_router.include_router(questions.wrong_book_router)
api_router.include_router(files.router)
api_router.include_router(focus.router)
api_router.include_router(focus.pet_router)
api_router.include_router(focus.coin_router)
api_router.include_router(ops.todos_router)
api_router.include_router(ops.reminders_router)
api_router.include_router(ops.notifications_router)
api_router.include_router(ops.calendar_router)
api_router.include_router(ops.courses_router)
api_router.include_router(ops.reports_router)
api_router.include_router(ops.demo_router)
