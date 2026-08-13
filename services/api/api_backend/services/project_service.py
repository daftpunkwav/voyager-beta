"""
项目业务逻辑 —— 筛选、序列化、导入（本地单机，无 user 维度）
"""
from uuid import UUID

from api_backend.models.project import Project, project_tags
from api_backend.schemas.project import (
    ImportRepoItem,
    ImportResult,
    ProjectCreate,
    ProjectOut,
    ProjectStats,
)
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession


def project_to_out(project: Project, tag_ids: list[str] | None = None) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        name=project.name,
        url=project.url,
        description=project.description,
        language=project.language,
        stars=project.stars,
        category_id=project.category_id,
        progress=project.progress,  # type: ignore[arg-type]
        tags=tag_ids or [],
        source=project.source,  # type: ignore[arg-type]
        imported_at=project.imported_at,
        updated_at=project.updated_at,
    )


async def load_tags_map(db: AsyncSession, project_ids: list[UUID]) -> dict[UUID, list[str]]:
    if not project_ids:
        return {}
    result = await db.execute(
        select(project_tags.c.project_id, project_tags.c.tag_id).where(
            project_tags.c.project_id.in_(project_ids)
        )
    )
    mapping: dict[UUID, list[str]] = {}
    for pid, tid in result.all():
        mapping.setdefault(pid, []).append(str(tid))
    return mapping


def apply_project_filters(
    query,
    *,
    keyword: str = "",
    lang: str = "",
    star_min: int = 0,
    star_max: int | None = None,
    progress: str = "",
    category_id: UUID | None = None,
    tag_id: UUID | None = None,
):
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            or_(Project.name.ilike(like), Project.description.ilike(like))
        )
    if lang:
        query = query.where(Project.language == lang)
    if star_min:
        query = query.where(Project.stars >= star_min)
    if star_max is not None:
        query = query.where(Project.stars <= star_max)
    if progress:
        query = query.where(Project.progress == progress)
    if category_id:
        query = query.where(Project.category_id == category_id)
    if tag_id:
        query = query.join(
            project_tags, Project.id == project_tags.c.project_id
        ).where(project_tags.c.tag_id == tag_id)
    return query


def apply_sort(query, sort: str):
    if sort == "stars":
        return query.order_by(Project.stars.desc())
    if sort == "name":
        return query.order_by(Project.name.asc())
    if sort == "updated_at":
        return query.order_by(Project.updated_at.desc().nullslast())
    return query.order_by(Project.imported_at.desc())


async def list_user_projects(
    db: AsyncSession,
    *,
    keyword: str = "",
    lang: str = "",
    star_min: int = 0,
    star_max: int | None = None,
    sort: str = "",
    progress: str = "",
    category_id: UUID | None = None,
    tag_id: UUID | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ProjectOut], int]:
    base = select(Project)
    base = apply_project_filters(
        base,
        keyword=keyword,
        lang=lang,
        star_min=star_min,
        star_max=star_max,
        progress=progress,
        category_id=category_id,
        tag_id=tag_id,
    )
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar_one()
    base = apply_sort(base, sort)
    offset = (page - 1) * page_size
    result = await db.execute(base.offset(offset).limit(page_size))
    projects = result.scalars().all()
    tag_map = await load_tags_map(db, [p.id for p in projects])
    items = [project_to_out(p, tag_map.get(p.id, [])) for p in projects]
    return items, total


# 语言 → 预设分类名（须与 seed_service.PRESET_CATEGORIES 名称一致）
_LANG_CATEGORY = {
    "TypeScript": "前端",
    "JavaScript": "前端",
    "Vue": "前端",
    "CSS": "前端",
    "HTML": "前端",
    "Svelte": "前端",
    "Python": "后端",
    "Go": "后端",
    "Rust": "后端",
    "Java": "后端",
    "C#": "后端",
    "PHP": "后端",
    "Ruby": "后端",
    "Kotlin": "其他",
    "Swift": "其他",
    "Dart": "其他",
    "C++": "其他",
    "C": "其他",
    "Shell": "DevOps",
    "Dockerfile": "DevOps",
    "HCL": "DevOps",
    "Jupyter Notebook": "AI/ML",
    "R": "AI/ML",
    "Lua": "其他",
    "Scala": "后端",
}


async def _resolve_category_id(db: AsyncSession, language: str | None):
    """按语言匹配预设/自定义分类，找不到则返回 None。"""
    if not language:
        return None
    cat_name = _LANG_CATEGORY.get(language)
    if not cat_name:
        return None
    from api_backend.models.category import Category

    result = await db.execute(select(Category).where(Category.name == cat_name))
    cat = result.scalars().first()
    return cat.id if cat else None


async def import_repos(
    db: AsyncSession,
    repos: list[ImportRepoItem],
) -> ImportResult:
    from api_backend.services.github_client import fetch_repo_info

    succeeded = 0
    failed = 0
    errors: list[dict] = []
    existing = await db.execute(select(Project.url))
    known_urls = {row[0] for row in existing.all()}

    for repo in repos:
        if repo.url in known_urls:
            failed += 1
            errors.append({"repo": f"{repo.owner}/{repo.repo}", "reason": "ALREADY_EXISTS"})
            continue

        meta: dict = {}
        try:
            meta = await fetch_repo_info(repo.owner, repo.repo)
        except Exception:
            meta = {}

        language = None if meta.get("error") else meta.get("language")
        description = None if meta.get("error") else meta.get("description")
        stars = 0 if meta.get("error") else int(meta.get("stars") or 0)
        category_id = await _resolve_category_id(db, language)

        project = Project(
            name=f"{repo.owner}/{repo.repo}",
            url=repo.url,
            source="github",
            description=description,
            language=language,
            stars=stars,
            category_id=category_id,
        )
        db.add(project)
        known_urls.add(repo.url)
        succeeded += 1

    await db.commit()
    summary = (
        f"成功导入 {succeeded} 个，失败 {failed} 个。"
        "已拉取 GitHub 元数据并按语言做降级分类；配置 LLM 后可在导入助手中由 Curator 精细分类。"
    )
    return ImportResult(succeeded=succeeded, failed=failed, summary=summary, errors=errors)


async def project_stats(db: AsyncSession) -> ProjectStats:
    result = await db.execute(select(Project))
    projects = result.scalars().all()
    by_progress: dict[str, int] = {}
    by_language: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for p in projects:
        by_progress[p.progress] = by_progress.get(p.progress, 0) + 1
        lang = p.language or "unknown"
        by_language[lang] = by_language.get(lang, 0) + 1
        cat = str(p.category_id) if p.category_id else "uncategorized"
        by_category[cat] = by_category.get(cat, 0) + 1
    return ProjectStats(
        total=len(projects),
        by_progress=by_progress,
        by_language=by_language,
        by_category=by_category,
    )


def build_project_from_create(data: ProjectCreate) -> Project:
    payload = data.model_dump(exclude={"tags"})
    return Project(**payload)


async def get_project(db: AsyncSession, project_id: UUID) -> Project | None:
    """按 id 查询项目；不存在返回 None。"""
    return await db.get(Project, project_id)


# 兼容旧名
get_project_owned_by_user = get_project
