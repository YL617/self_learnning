from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.models import (
    Course,
    CourseChapter,
    DailyStat,
    FocusSession,
    PlanItem,
    Reminder,
    StudyPlan,
    Todo,
    User,
    WrongBookItem,
)
from app.schemas.ops import (
    CalendarEventOut,
    CourseOut,
    DemoSeedOut,
    NotificationOut,
    ReminderCreate,
    ReminderOut,
    TodoCreate,
    TodoOut,
    TodoUpdate,
    WeeklyReportOut,
)

settings = get_settings()

todos_router = APIRouter(prefix="/todos", tags=["todos"])
reminders_router = APIRouter(prefix="/reminders", tags=["reminders"])
notifications_router = APIRouter(prefix="/notifications", tags=["notifications"])
calendar_router = APIRouter(prefix="/calendar", tags=["calendar"])
courses_router = APIRouter(prefix="/courses", tags=["courses"])
reports_router = APIRouter(prefix="/reports", tags=["reports"])
demo_router = APIRouter(prefix="/demo", tags=["demo"])


def _seed_courses(db: Session) -> None:
    if db.scalar(select(Course).limit(1)) is not None:
        return
    data = [
        (
            "数据结构与算法",
            "B站",
            "https://www.bilibili.com/",
            "从数组、链表到树与图的系统讲解，适合复习数据结构。",
            ["线性表", "栈与队列", "树与二叉树", "图与搜索"],
        ),
        (
            "计算机网络",
            "中国大学MOOC",
            "https://www.icourse163.org/",
            "覆盖 OSI 七层模型、TCP/IP 协议栈与常见网络问题。",
            ["网络体系结构", "传输层", "网络层", "应用层"],
        ),
        (
            "C语言程序设计",
            "B站",
            "https://www.bilibili.com/",
            "从语法到指针和内存管理的入门与进阶课程。",
            ["基础语法", "函数", "指针", "结构体"],
        ),
    ]
    for title, platform, url, description, chapters in data:
        course = Course(
            title=title,
            platform=platform,
            url=url,
            description=description,
        )
        for index, chapter in enumerate(chapters, start=1):
            course.chapters.append(
                CourseChapter(title=chapter, order_index=index)
            )
        db.add(course)
    db.commit()


@todos_router.get("", response_model=list[TodoOut])
def list_todos(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Todo]:
    return list(
        db.scalars(
            select(Todo)
            .where(Todo.user_id == current_user.id)
            .order_by(Todo.due_date.asc())
        ).all()
    )


@todos_router.post("", response_model=TodoOut, status_code=status.HTTP_201_CREATED)
def create_todo(
    data: TodoCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Todo:
    todo = Todo(user_id=current_user.id, **data.model_dump())
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return todo


@todos_router.api_route("/{todo_id}", response_model=TodoOut, methods=["PATCH", "PUT"])
def update_todo(
    todo_id: int,
    data: TodoUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Todo:
    todo = db.scalar(
        select(Todo).where(Todo.id == todo_id, Todo.user_id == current_user.id)
    )
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待办不存在")
    if data.completed is not None:
        todo.completed = data.completed
    db.commit()
    db.refresh(todo)
    return todo


@todos_router.delete("/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_todo(
    todo_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    todo = db.scalar(
        select(Todo).where(Todo.id == todo_id, Todo.user_id == current_user.id)
    )
    if todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="待办不存在")
    db.delete(todo)
    db.commit()


@calendar_router.get("", response_model=list[CalendarEventOut])
def get_calendar(
    month: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[CalendarEventOut]:
    try:
        start = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="月份格式应为 YYYY-MM")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    plan_items = db.scalars(
        select(PlanItem)
        .join(StudyPlan)
        .where(
            StudyPlan.user_id == current_user.id,
            PlanItem.scheduled_date.between(start, end),
        )
    ).all()
    todos = db.scalars(
        select(Todo).where(
            Todo.user_id == current_user.id,
            Todo.due_date.between(start, end),
        )
    ).all()

    events: list[CalendarEventOut] = [
        CalendarEventOut(
            date=item.scheduled_date,
            title=item.title,
            kind="plan_item",
            id=item.id,
            completed=item.completed,
        )
        for item in plan_items
    ]
    events.extend(
        CalendarEventOut(
            date=todo.due_date,
            title=todo.title,
            kind="todo",
            id=todo.id,
            completed=todo.completed,
        )
        for todo in todos
    )
    return sorted(events, key=lambda event: (event.date, event.kind))


@reminders_router.get("", response_model=list[ReminderOut])
def list_reminders(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[Reminder]:
    return list(
        db.scalars(
            select(Reminder)
            .where(Reminder.user_id == current_user.id)
            .order_by(Reminder.remind_at.asc())
        ).all()
    )


@reminders_router.post("", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
def create_reminder(
    data: ReminderCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Reminder:
    reminder = Reminder(user_id=current_user.id, **data.model_dump())
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


@reminders_router.delete("/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reminder(
    reminder_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    reminder = db.scalar(
        select(Reminder).where(
            Reminder.id == reminder_id,
            Reminder.user_id == current_user.id,
        )
    )
    if reminder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="提醒不存在")
    db.delete(reminder)
    db.commit()


@notifications_router.get("", response_model=list[NotificationOut])
def list_notifications(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[NotificationOut]:
    now = datetime.now(timezone.utc)
    reminders = db.scalars(
        select(Reminder).where(
            Reminder.user_id == current_user.id,
            Reminder.remind_at <= now,
            Reminder.dismissed.is_(False),
        )
    ).all()
    overdue_items = db.scalars(
        select(PlanItem)
        .join(StudyPlan)
        .where(
            StudyPlan.user_id == current_user.id,
            PlanItem.completed.is_(False),
            PlanItem.scheduled_date < date.today(),
        )
    ).all()
    notifications = [
        NotificationOut(id=item.id, kind="reminder", title=item.title, remind_at=item.remind_at)
        for item in reminders
    ]
    notifications.extend(
        NotificationOut(id=item.id, kind="plan_item", title=f"未完成任务：{item.title}")
        for item in overdue_items
    )
    return notifications[:20]


@notifications_router.api_route(
    "/{notification_id}/dismiss",
    status_code=status.HTTP_204_NO_CONTENT,
    methods=["PATCH", "PUT"],
)
def dismiss_notification(
    notification_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    reminder = db.scalar(
        select(Reminder).where(
            Reminder.id == notification_id,
            Reminder.user_id == current_user.id,
        )
    )
    if reminder is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="通知不存在")
    reminder.dismissed = True
    reminder.triggered = True
    db.commit()


@courses_router.get("", response_model=list[CourseOut])
def list_courses(
    db: Annotated[Session, Depends(get_db)],
) -> list[Course]:
    _seed_courses(db)
    return list(
        db.scalars(
            select(Course).options(selectinload(Course.chapters))
        ).all()
    )


@reports_router.get("/weekly", response_model=WeeklyReportOut)
def weekly_report(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> WeeklyReportOut:
    end = date.today()
    start = end - timedelta(days=6)
    stats = db.scalars(
        select(DailyStat).where(
            DailyStat.user_id == current_user.id,
            DailyStat.stat_date.between(start, end),
        )
    ).all()
    sessions = db.scalars(
        select(FocusSession).where(
            FocusSession.user_id == current_user.id,
            FocusSession.completed.is_(True),
            FocusSession.ended_at >= datetime.combine(start, time.min),
            FocusSession.ended_at <= datetime.combine(end, time.max),
        )
    ).all()
    wrong_added = len(
        db.scalars(
            select(WrongBookItem).where(
                WrongBookItem.user_id == current_user.id,
                WrongBookItem.created_at >= datetime.combine(start, time.min),
            )
        ).all()
    )
    return WeeklyReportOut(
        start_date=start,
        end_date=end,
        focus_minutes=sum(stat.focus_minutes for stat in stats),
        sessions=len(sessions),
        answered=sum(stat.answered_count for stat in stats),
        correct=sum(stat.correct_count for stat in stats),
        coins_earned=sum(stat.coin_earned for stat in stats),
        wrong_added=wrong_added,
    )


@demo_router.post("/seed", response_model=DemoSeedOut)
def seed_demo_data(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> DemoSeedOut:
    if settings.APP_ENV != "dev":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅演示环境可用")
    todos = [
        Todo(user_id=current_user.id, title="整理本周笔记", due_date=date.today()),
        Todo(user_id=current_user.id, title="完成一章练习题", due_date=date.today()),
        Todo(user_id=current_user.id, title="复习错题本", due_date=date.today() + timedelta(days=1)),
    ]
    reminders = [
        Reminder(
            user_id=current_user.id,
            title="晚上八点复习计划",
            remind_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
        Reminder(
            user_id=current_user.id,
            title="明天完成待办",
            remind_at=datetime.now(timezone.utc) + timedelta(days=1),
        ),
    ]
    sessions = [
        FocusSession(
            user_id=current_user.id,
            task_label="数据结构复习",
            started_at=datetime.now(timezone.utc) - timedelta(days=1, hours=1),
            ended_at=datetime.now(timezone.utc) - timedelta(days=1),
            duration_minutes=25,
            completed=True,
        ),
        FocusSession(
            user_id=current_user.id,
            task_label="错题复习",
            started_at=datetime.now(timezone.utc) - timedelta(hours=1),
            ended_at=datetime.now(timezone.utc),
            duration_minutes=25,
            completed=True,
        ),
    ]
    db.add_all(todos + reminders + sessions)
    _seed_courses(db)
    db.commit()
    return DemoSeedOut(
        message="演示数据填充完成",
        todos=len(todos),
        reminders=len(reminders),
        sessions=len(sessions),
        courses=3,
    )
