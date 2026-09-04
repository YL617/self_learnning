"""真实课程推荐服务。

本模块不再调用大模型生成课程链接，而是维护一份经过校验的真实公开课目录，
根据学习计划的科目、目标、任务标题以及学生基本信息（专业/年级/薄弱科目/
目标）进行匹配，推荐可直达课程页的课程。同时提供课程链接健康探活，用于
服务端定时校验（不占用页面请求），并记录课程的保存/忽略反馈以调整排序。
"""

from __future__ import annotations

import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Course, CourseChapter, CourseRecommendation, StudyPlan, User

# 真实公开课目录：url 均为可直接访问的具体课程页，非平台首页。
# keywords 用于和计划中的科目/目标/任务标题匹配；level 与 language 用于个性化排序。
COURSE_CATALOG: list[dict[str, Any]] = [
    {
        "title": "数据结构（浙江大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/ZJU-93001",
        "subject": "数据结构",
        "level": "入门",
        "language": "zh",
        "keywords": ["数据结构", "data structure", "线性表", "树", "图", "查找", "排序"],
        "description": "浙江大学名师主讲的数据结构课程，覆盖线性表、树与图等核心内容，配套编程练习。",
        "chapters": ["线性表", "栈与队列", "树与二叉树", "图", "查找与排序"],
    },
    {
        "title": "数据结构（清华大学 · 邓俊辉）",
        "platform": "学堂在线",
        "url": "https://www.xuetangx.com/course/THU08091000384/29593888",
        "subject": "数据结构",
        "level": "进阶",
        "language": "zh",
        "keywords": ["数据结构", "data structure", "向量", "列表", "树", "图", "算法"],
        "description": "邓俊辉教授的经典数据结构课程，讲解抽象数据类型与各类数据结构的设计与实现。",
        "chapters": ["向量", "列表", "栈与队列", "树", "图"],
    },
    {
        "title": "王道考研数据结构（B站）",
        "platform": "哔哩哔哩",
        "url": "https://www.bilibili.com/video/BV1b7411N798",
        "subject": "数据结构",
        "level": "考研",
        "language": "zh",
        "keywords": ["数据结构", "考研", "408", "计算机", "线性表", "树", "图"],
        "description": "王道考研数据结构系列视频，适合考研复习与期末突击，覆盖核心考点。",
        "chapters": ["线性表", "栈与队列", "树与二叉树", "图", "查找", "排序"],
    },
    {
        "title": "计算机网络系统（电子科技大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/UESTC-1003039003",
        "subject": "计算机网络",
        "level": "进阶",
        "language": "zh",
        "keywords": ["计算机网络", "网络", "tcp", "ip", "osi", "http"],
        "description": "电子科技大学《计算机网络系统》，覆盖 OSI 七层模型、TCP/IP 协议栈与常见网络问题。",
        "chapters": ["网络体系结构", "传输层", "网络层", "应用层"],
    },
    {
        "title": "程序设计入门——C语言（浙江大学 · 翁恺）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/ZJU-199001",
        "subject": "C语言",
        "level": "入门",
        "language": "zh",
        "keywords": ["c语言", "c 语言", "c程序设计", "程序设计", "翁恺", "指针"],
        "description": "翁恺老师的程序设计入门课程，从零基础讲解 C 语言语法、指针与内存管理。",
        "chapters": ["基础语法", "函数", "指针", "结构体"],
    },
    {
        "title": "C语言程序设计（哈尔滨工业大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/HIT-69005",
        "subject": "C语言",
        "level": "进阶",
        "language": "zh",
        "keywords": ["c语言", "c 语言", "程序设计", "计算机", "指针", "内存"],
        "description": "哈尔滨工业大学国家精品课程，系统讲授 C 语言语法、指针与模块化程序设计。",
        "chapters": ["基础语法", "数组与指针", "函数", "结构体与文件"],
    },
    {
        "title": "Python程序设计（浙江大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/ZJU-1206456840",
        "subject": "Python",
        "level": "入门",
        "language": "zh",
        "keywords": ["python", "程序设计", "编程", "脚本", "爬虫"],
        "description": "面向零基础学生的 Python 入门课，覆盖语法、容器、函数与文件操作。",
        "chapters": ["Python入门", "数据类型与容器", "控制语句", "函数与文件"],
    },
    {
        "title": "Java程序设计（北京大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/PKU-1001941004",
        "subject": "Java",
        "level": "入门",
        "language": "zh",
        "keywords": ["java", "面向对象", "对象", "程序设计", "jvm"],
        "description": "北京大学 Java 课程，讲解面向对象思想与 Java 语言基础。",
        "chapters": ["Java基础", "面向对象", "集合框架", "异常处理"],
    },
    {
        "title": "操作系统（清华大学 · 向勇/陈渝）",
        "platform": "学堂在线",
        "url": "https://www.xuetangx.com/course/THU08091000267/5883104",
        "subject": "操作系统",
        "level": "进阶",
        "language": "zh",
        "keywords": ["操作系统", "os", "进程", "线程", "调度", "内存管理", "文件系统"],
        "description": "清华大学操作系统课程，基于 Linux 讲解进程、内存、文件与设备管理。",
        "chapters": ["进程与线程", "内存管理", "文件系统", "设备管理"],
    },
    {
        "title": "数据库系统概论（中国人民大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/RUC-488001",
        "subject": "数据库",
        "level": "进阶",
        "language": "zh",
        "keywords": ["数据库", "sql", "关系模型", "事务", "mysql", "数据"],
        "description": "人大数据库系统概论，讲授关系模型、SQL、事务与数据管理核心原理。",
        "chapters": ["关系模型", "SQL语言", "数据库设计", "事务与并发"],
    },
    {
        "title": "数据库系统概论（中国人民大学 · 学堂在线）",
        "platform": "学堂在线",
        "url": "https://www.xuetangx.com/course/ruc08091015722/29606054",
        "subject": "数据库",
        "level": "进阶",
        "language": "zh",
        "keywords": ["数据库", "sql", "关系", "事务", "并发", "数据"],
        "description": "配套《数据库系统概论》教材的学堂在线课程，适合系统复习数据库原理。",
        "chapters": ["关系模型", "SQL", "数据库设计", "事务"],
    },
    {
        "title": "机器学习（吴恩达 Andrew Ng · Coursera）",
        "platform": "Coursera",
        "url": "https://www.coursera.org/learn/machine-learning",
        "subject": "机器学习",
        "level": "入门",
        "language": "en",
        "keywords": ["机器学习", "machine learning", "深度学习", "ai", "人工智能", "神经网络"],
        "description": "吴恩达经典机器学习课程，涵盖回归、分类、神经网络与推荐系统（英文）。",
        "chapters": ["线性回归", "逻辑回归", "神经网络", "支持向量机", "聚类"],
    },
    {
        "title": "机器学习（浙江大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/ZJU-1206573810",
        "subject": "机器学习",
        "level": "进阶",
        "language": "zh",
        "keywords": ["机器学习", "人工智能", "深度学习", "神经网络", "算法"],
        "description": "浙江大学机器学习课程，介绍监督学习、无监督学习与常用模型。",
        "chapters": ["监督学习", "无监督学习", "模型评估", "深度学习入门"],
    },
    {
        "title": "高等数学（同济大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/TONGJI-53004",
        "subject": "高等数学",
        "level": "入门",
        "language": "zh",
        "keywords": ["高等数学", "高数", "微积分", "极限", "导数", "积分", "数学"],
        "description": "同济大学《高等数学》MOOC，覆盖极限、微积分与常微分方程。",
        "chapters": ["函数与极限", "导数与微分", "不定积分", "定积分", "多元函数"],
    },
    {
        "title": "线性代数（同济大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/TONGJI-481001",
        "subject": "线性代数",
        "level": "入门",
        "language": "zh",
        "keywords": ["线性代数", "矩阵", "向量", "行列式", "特征值", "数学"],
        "description": "同济大学线性代数课程，系统讲解矩阵、行列式、向量组与特征值。",
        "chapters": ["行列式", "矩阵", "向量组", "特征值与特征向量"],
    },
    {
        "title": "概率论与数理统计（山东大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/SDU-1001945006",
        "subject": "概率论",
        "level": "入门",
        "language": "zh",
        "keywords": ["概率论", "数理统计", "概率", "随机", "统计", "数学"],
        "description": "山东大学概率论与数理统计课程，覆盖随机变量、分布与统计推断。",
        "chapters": ["随机事件", "随机变量", "数字特征", "数理统计"],
    },
    {
        "title": "大学英语（备战四级）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/QZSFXY-1206685832",
        "subject": "英语",
        "level": "入门",
        "language": "zh",
        "keywords": ["英语", "四级", "六级", "cet", "大学英语", "语法", "词汇"],
        "description": "面向大学英语四六级备考的课程，提供专项学习模块与真题训练。",
        "chapters": ["词汇", "听力", "阅读", "写作", "翻译"],
    },
    {
        "title": "算法设计与分析（哈尔滨工业大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/HIT-356006",
        "subject": "算法",
        "level": "进阶",
        "language": "zh",
        "keywords": ["算法", "算法设计", "递归", "分治", "动态规划", "贪心", "复杂度"],
        "description": "哈尔滨工业大学算法设计与分析课程，讲解递归、分治、动态规划与贪心策略。",
        "chapters": ["算法基础", "分治", "动态规划", "贪心", "回溯"],
    },
    {
        "title": "算法设计与分析（北京大学）",
        "platform": "中国大学MOOC",
        "url": "https://www.icourse163.org/course/PKU-1002525003",
        "subject": "算法",
        "level": "进阶",
        "language": "zh",
        "keywords": ["算法", "算法设计", "动态规划", "贪心", "图", "搜索", "复杂度"],
        "description": "北京大学算法设计与分析课程，结合数据结构讲解常用算法策略。",
        "chapters": ["分治", "动态规划", "贪心", "图算法", "复杂度分析"],
    },
]


# 以下域名若 path 为空则视为“平台首页”，不是具体课程页。
_HOME_HOSTS = {
    "www.icourse163.org",
    "course.icourse163.org",
    "www.bilibili.com",
    "www.xuetangx.com",
    "next.xuetangx.com",
    "www.coursera.org",
    "higher.smartedu.cn",
}

_LEVEL_ORDER = {"入门": 0, "进阶": 1, "考研": 2}
_GOAL_TERMS = [
    "考研",
    "考硏",
    "四级",
    "六级",
    "期末",
    "竞赛",
    "入门",
    "进阶",
    "就业",
    "面试",
    "应试",
    "提高",
    "突破",
]


def is_platform_home(url: str) -> bool:
    """判断链接是否只是平台首页（而非具体课程页）。"""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    host = (parsed.hostname or "").lower()
    if host not in _HOME_HOSTS:
        return False
    return (parsed.path or "").strip("/") == ""


def _keywords_text(plan: StudyPlan) -> str:
    parts = [plan.title or "", plan.goal or ""]
    for item in plan.items:
        parts.append(item.title or "")
        parts.append(item.subject or "")
    return " ".join(parts).lower()


def _profile_context(user: User | None, plan_text: str) -> dict[str, Any]:
    profile = getattr(user, "profile", None) if user else None
    major = (profile.major if profile else None) or ""
    grade = (profile.grade if profile else None) or ""
    goals = (profile.goals if profile else None) or ""
    weak = (profile.weak_subjects if profile else None) or ""
    school = (profile.school_level if profile else None) or ""
    combined = f"{plan_text} {major} {goals} {weak} {grade} {school}".lower()
    low = (goals + " " + grade + " " + school).lower()
    desired_level = "进阶"
    if any(k in low for k in ["考研", "考硏", "升学", "研究生", "应试"]):
        desired_level = "考研"
    elif any(
        k in (grade + " " + goals).lower()
        for k in ["大一", "大二", "大三", "零基础", "入门", "高中", "初三", "初学者"]
    ):
        desired_level = "入门"
    return {
        "full_text": combined,
        "weak_lower": weak.lower(),
        "goals_lower": goals.lower(),
        "desired_level": desired_level,
    }


def _base_score(text_lower: str, course: dict[str, Any]) -> float:
    """基础相关度：仅看课程与计划科目/知识点的匹配。"""
    score = 0.0
    for keyword in course.get("keywords", []):
        if str(keyword).lower() in text_lower:
            score += 1.0
    subject = str(course.get("subject") or "").lower()
    if subject and subject in text_lower:
        score += 3.0
    return score


def _personal_bonus(
    course: dict[str, Any],
    ctx: dict[str, Any] | None,
    counters: dict[str, Any],
) -> float:
    bonus = 0.0
    if ctx:
        subject = str(course.get("subject") or "").lower()
        if subject and subject in ctx["weak_lower"]:
            bonus += 2.0
        title_desc = f"{course.get('title', '')} {course.get('description', '')}".lower()
        for term in _GOAL_TERMS:
            if term in ctx["goals_lower"] and term in title_desc:
                bonus += 1.0
        desired = ctx["desired_level"]
        level = str(course.get("level") or "进阶")
        if level == desired:
            bonus += 1.5
        elif _LEVEL_ORDER.get(level, 1) == _LEVEL_ORDER.get(desired, 1):
            bonus += 0.5
        if str(course.get("language") or "zh") == "zh":
            bonus += 0.2
    info = counters.get(course["title"], {})
    bonus -= int(info.get("dismiss", 0)) * 0.5
    bonus += int(info.get("save", 0)) * 0.3
    return bonus


def _pick_courses(
    text_lower: str,
    ctx: dict[str, Any] | None,
    counters: dict[str, Any],
    limit: int = 5,
) -> list[dict[str, Any]]:
    scored = [
        (
            course,
            _base_score(text_lower, course) + _personal_bonus(course, ctx, counters),
            _base_score(text_lower, course),
        )
        for course in COURSE_CATALOG
    ]
    relevant = [item for item in scored if item[2] > 0]
    relevant.sort(
        key=lambda item: (
            -item[1],
            COURSE_CATALOG.index(item[0]),
        )
    )
    if relevant:
        return [course for course, total, base in relevant[:limit]]
    # 无匹配时回退到目录前几门经典课程，保证推荐卡片不为空。
    default = sorted(scored, key=lambda item: (COURSE_CATALOG.index(item[0]),))
    return [course for course, total, base in default[:limit]]


def _build_counters(db: Session) -> dict[str, dict[str, int]]:
    counters: dict[str, dict[str, int]] = {}
    for course in db.scalars(select(Course)).all():
        counters[course.title] = {
            "dismiss": course.dismiss_count or 0,
            "save": course.save_count or 0,
        }
    return counters


def _ensure_course(db: Session, catalog: dict[str, Any]) -> Course | None:
    existing = db.scalar(select(Course).where(Course.title == catalog["title"]))
    if existing is not None:
        # 回填历史课程缺失的元数据。
        if not existing.level:
            existing.level = catalog.get("level") or "进阶"
        if not existing.language:
            existing.language = catalog.get("language") or "zh"
        return existing
    course = Course(
        title=catalog["title"],
        platform=catalog["platform"],
        url=catalog["url"],
        description=catalog.get("description"),
        level=catalog.get("level") or "进阶",
        language=catalog.get("language") or "zh",
    )
    for index, chapter in enumerate(catalog.get("chapters", []), start=1):
        course.chapters.append(CourseChapter(title=chapter, order_index=index))
    db.add(course)
    db.flush()
    return course


def ensure_catalog_courses(db: Session) -> None:
    """清理历史“平台首页”占位课程，并补进真实课程目录（按标题去重）。"""
    for course in db.scalars(select(Course)).all():
        if is_platform_home(course.url):
            db.delete(course)
    for catalog in COURSE_CATALOG:
        _ensure_course(db, catalog)
    db.commit()


def recommend_courses_for_plan(
    db: Session,
    user_id: int,
    plan: StudyPlan,
    limit: int = 5,
) -> list[CourseRecommendation]:
    text_lower = _keywords_text(plan)
    user = db.get(User, user_id)
    ctx = _profile_context(user, text_lower)
    counters = _build_counters(db)
    picks = _pick_courses(text_lower, ctx, counters, limit=limit)

    # 清理历史遗留推荐：未关联课程的旧 AI 推荐、指向“平台首页”的空链接。
    stale = db.scalars(
        select(CourseRecommendation).where(
            CourseRecommendation.plan_id == plan.id,
            CourseRecommendation.user_id == user_id,
            CourseRecommendation.status.in_(("pending", "saved")),
        )
    ).all()
    for rec in stale:
        if rec.course_id is None or is_platform_home(rec.url):
            db.delete(rec)
    db.flush()

    # 跳过同一计划下已经存在的推荐，避免重复生成。
    existing = {
        rec.course_id
        for rec in db.scalars(
            select(CourseRecommendation).where(
                CourseRecommendation.plan_id == plan.id,
                CourseRecommendation.user_id == user_id,
            )
        ).all()
    }

    created: list[CourseRecommendation] = []
    for catalog in picks:
        course = _ensure_course(db, catalog)
        if course is None or course.id in existing:
            continue
        rec = CourseRecommendation(
            user_id=user_id,
            plan_id=plan.id,
            course_id=course.id,
            title=catalog["title"],
            platform=catalog["platform"],
            url=catalog["url"],
            description=catalog.get("description"),
            subject=catalog.get("subject"),
            level=catalog.get("level"),
            language=catalog.get("language"),
            status="pending",
        )
        db.add(rec)
        created.append(rec)
    db.commit()
    return created


def _get_own_recommendation(
    db: Session,
    user_id: int,
    recommendation_id: int,
) -> CourseRecommendation:
    rec = db.scalar(
        select(CourseRecommendation).where(
            CourseRecommendation.id == recommendation_id,
            CourseRecommendation.user_id == user_id,
        )
    )
    if rec is None:
        raise ValueError("课程推荐不存在")
    return rec


def save_course_recommendation(
    db: Session,
    user_id: int,
    recommendation_id: int,
) -> CourseRecommendation:
    rec = _get_own_recommendation(db, user_id, recommendation_id)
    if rec.status != "saved":
        if rec.course_id is None:
            course = _ensure_course(
                db,
                {
                    "title": rec.title,
                    "platform": rec.platform,
                    "url": rec.url,
                    "description": rec.description,
                    "level": rec.level,
                    "language": rec.language,
                },
            )
            rec.course_id = course.id if course else None
        if rec.course_id:
            course = db.get(Course, rec.course_id)
            if course:
                course.save_count = (course.save_count or 0) + 1
        rec.status = "saved"
        db.commit()
        db.refresh(rec)
    return rec


def dismiss_course_recommendation(
    db: Session,
    user_id: int,
    recommendation_id: int,
) -> CourseRecommendation:
    rec = _get_own_recommendation(db, user_id, recommendation_id)
    if rec.status != "dismissed":
        if rec.course_id:
            course = db.get(Course, rec.course_id)
            if course:
                course.dismiss_count = (course.dismiss_count or 0) + 1
        rec.status = "dismissed"
        db.commit()
        db.refresh(rec)
    return rec


def _probe_url(url: str, timeout: int = 8) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = getattr(resp, "status", 200)
            if 200 <= code < 400:
                return {"status": "ok", "http_status": code, "error": None}
            return {"status": "bad", "http_status": code, "error": f"HTTP {code}"}
    except urllib.error.HTTPError as exc:
        return {"status": "bad", "http_status": exc.code, "error": f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "bad", "http_status": None, "error": str(exc)[:200]}


def check_catalog_health(
    db: Session,
    max_workers: int = 6,
    timeout: int = 8,
) -> dict[str, Any]:
    """校验全部目录课程链接的健康状态，仅返回统计，不阻塞页面请求。

    该函数应由 Celery 定时任务或管理端手动触发，避免在普通页面请求中做外网访问。
    """
    ensure_catalog_courses(db)
    tasks = [(catalog["title"], catalog["url"]) for catalog in COURSE_CATALOG]
    ok = bad = 0
    checked_at = datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(
            lambda item: (item[0], item[1], _probe_url(item[1], timeout)),
            tasks,
        )
        for title, url, result in results:
            course = db.scalar(select(Course).where(Course.title == title))
            if course is None:
                continue
            course.health_status = result["status"]
            course.http_status = result["http_status"]
            course.health_checked_at = checked_at
            course.health_error = result["error"]
            if result["status"] == "ok":
                ok += 1
            else:
                bad += 1
    db.commit()
    return {"ok": ok, "bad": bad, "checked": len(tasks)}
