"""
笔记 API —— 项目内笔记 CRUD + 全量列表（本地单机）
"""
from uuid import UUID

from api_backend.api.deps import get_db
from api_backend.core.responses import wrap_data
from api_backend.models.note import Note
from api_backend.models.project import Project
from api_backend.schemas.common import DataResponse
from api_backend.schemas.note import NoteCreate, NoteOut, NoteUpdate
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/notes", tags=["notes"])


async def _get_project(db: AsyncSession, project_id: UUID) -> Project:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "PROJECT_NOT_FOUND", "message": "项目不存在"},
        )
    return project


async def _get_note(db: AsyncSession, note_id: UUID) -> Note:
    note = await db.get(Note, note_id)
    if not note:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail={"code": "NOTE_NOT_FOUND", "message": "笔记不存在"},
        )
    return note


@router.get("/", response_model=DataResponse[list[NoteOut]])
async def list_all_notes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Note))
    items = [NoteOut.model_validate(n) for n in result.scalars().all()]
    return wrap_data(items)


@router.get("/projects/{project_id}/notes", response_model=DataResponse[list[NoteOut]])
async def list_notes(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await _get_project(db, project_id)
    result = await db.execute(select(Note).where(Note.project_id == project_id))
    items = [NoteOut.model_validate(n) for n in result.scalars().all()]
    return wrap_data(items)


@router.get("/{note_id}", response_model=DataResponse[NoteOut])
async def get_note(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    note = await _get_note(db, note_id)
    return wrap_data(NoteOut.model_validate(note))


@router.post("/projects/{project_id}/notes", response_model=DataResponse[NoteOut])
async def create_note(
    project_id: UUID,
    data: NoteCreate,
    db: AsyncSession = Depends(get_db),
):
    await _get_project(db, project_id)
    note = Note(project_id=project_id, **data.model_dump())
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return wrap_data(NoteOut.model_validate(note))


@router.put("/{note_id}", response_model=DataResponse[NoteOut])
async def update_note(
    note_id: UUID,
    data: NoteUpdate,
    db: AsyncSession = Depends(get_db),
):
    note = await _get_note(db, note_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(note, key, value)
    await db.commit()
    await db.refresh(note)
    return wrap_data(NoteOut.model_validate(note))


@router.delete("/{note_id}", response_model=DataResponse[dict])
async def delete_note(
    note_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    note = await _get_note(db, note_id)
    await db.delete(note)
    await db.commit()
    return wrap_data({"success": True})
