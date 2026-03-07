from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.admin.database import get_db
from app.user.dependencies import get_current_user
from app.user.models import User
from app.user.practice_schemas import (
    PracticeAttemptOut,
    PracticeAttemptRequest,
    PracticeBookmarkToggleOut,
    PracticeBootstrapOut,
    PracticeQuestionListOut,
)
from app.user.practice_service import (
    list_practice_questions,
    practice_bootstrap,
    submit_practice_attempt,
    toggle_question_bookmark,
)


router = APIRouter(prefix='/practice', tags=['User Practice'])


@router.get('/bootstrap', response_model=PracticeBootstrapOut)
def get_practice_bootstrap(
    exam_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PracticeBootstrapOut:
    return practice_bootstrap(db, user=current_user, exam_id=exam_id)


@router.get('/questions', response_model=PracticeQuestionListOut)
def get_practice_questions(
    exam_id: int | None = Query(default=None),
    subject_ids: list[int] | None = Query(default=None),
    difficulties: list[str] | None = Query(default=None),
    question_types: list[str] | None = Query(default=None),
    pyq_year: int | None = Query(default=None),
    bookmarked_only: bool = Query(default=False),
    shuffle: bool = Query(default=False),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PracticeQuestionListOut:
    return list_practice_questions(
        db,
        user=current_user,
        exam_id=exam_id,
        subject_ids=subject_ids,
        difficulties=difficulties,
        question_types=question_types,
        pyq_year=pyq_year,
        skip=skip,
        limit=limit,
        bookmarked_only=bookmarked_only,
        shuffle=shuffle,
    )


@router.post('/questions/{question_id}/attempt', response_model=PracticeAttemptOut)
def create_practice_attempt(
    question_id: str,
    payload: PracticeAttemptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PracticeAttemptOut:
    return submit_practice_attempt(db, user=current_user, question_id=question_id, selected_option=payload.selected_option)


@router.post('/questions/{question_id}/bookmark', response_model=PracticeBookmarkToggleOut)
def toggle_bookmark(
    question_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PracticeBookmarkToggleOut:
    return PracticeBookmarkToggleOut(
        question_id=question_id,
        is_bookmarked=toggle_question_bookmark(db, user=current_user, question_id=question_id),
    )
