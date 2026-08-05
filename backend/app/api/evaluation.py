"""Stage 2 evaluation dataset and asynchronous run endpoints."""

from typing import Annotated
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.core.config import get_settings
from app.db.models.evaluation import EvalCase, EvalDataset, EvalRun
from app.db.session import get_session
from app.evaluation.service import (
    add_manual_cases,
    compare_runs,
    create_dataset,
    create_eval_run,
    list_runs,
    refresh_dataset_case_count,
    review_case,
)
from app.schemas.evaluation import (
    DatasetCreateRequest,
    DatasetStatsResponse,
    EvalCaseResponse,
    EvalCaseSource,
    EvalCompareResponse,
    EvalDatasetResponse,
    EvalRunAccepted,
    EvalRunCreateRequest,
    EvalRunListResponse,
    EvalRunResponse,
    EvalRunStatus,
    ManualCasesRequest,
    ReviewCaseRequest,
    SyntheticGenerationAccepted,
    SyntheticGenerationRequest,
)

router = APIRouter(prefix="/eval", tags=["evaluation"])


@router.post("/datasets", response_model=EvalDatasetResponse, status_code=status.HTTP_201_CREATED)
async def create_eval_dataset(
    request: DatasetCreateRequest,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalDatasetResponse:
    dataset = await create_dataset(
        session,
        user_id=current_user_id,
        name=request.name,
        version_name=request.version,
        construction_method=request.construction_method,
    )
    await session.commit()
    return await _dataset_response(session, dataset)


@router.get("/datasets", response_model=list[EvalDatasetResponse])
async def list_eval_datasets(
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[EvalDatasetResponse]:
    datasets = list(
        (
            await session.scalars(
                select(EvalDataset)
                .where(EvalDataset.user_id == current_user_id)
                .order_by(EvalDataset.created_at.desc())
            )
        ).all()
    )
    return [await _dataset_response(session, dataset) for dataset in datasets]


@router.post(
    "/datasets/{dataset_id}/cases/manual",
    response_model=list[EvalCaseResponse],
    status_code=status.HTTP_201_CREATED,
)
async def add_manual_eval_cases(
    dataset_id: UUID,
    request: ManualCasesRequest,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[EvalCaseResponse]:
    dataset = await _owned_dataset(session, dataset_id, current_user_id)
    try:
        cases = await add_manual_cases(
            session,
            dataset_id=dataset.id,
            cases=[
                (item.query, item.expected_chunk_ids, item.review_note)
                for item in request.cases
            ],
        )
        await session.commit()
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error
    return [_case_response(case) for case in cases]


@router.post(
    "/datasets/{dataset_id}/synthetic",
    response_model=SyntheticGenerationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_synthetic_generation(
    dataset_id: UUID,
    request: SyntheticGenerationRequest,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SyntheticGenerationAccepted:
    await _owned_dataset(session, dataset_id, current_user_id)
    try:
        redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        try:
            await redis.enqueue_job(
                "generate_eval_dataset",
                str(dataset_id),
                request.count,
                request.seed,
                request.mode,
                _job_id=f"eval-dataset:{dataset_id}:{request.seed}:{request.count}",
            )
        finally:
            await redis.aclose()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dataset generation could not be queued; retry when the worker is available.",
        ) from error
    return SyntheticGenerationAccepted(dataset_id=dataset_id, status="queued", count=request.count)


@router.get("/datasets/{dataset_id}/cases", response_model=list[EvalCaseResponse])
async def list_eval_cases(
    dataset_id: UUID,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[EvalCaseResponse]:
    await _owned_dataset(session, dataset_id, current_user_id)
    cases = list(
        (
            await session.scalars(
                select(EvalCase)
                .where(EvalCase.dataset_id == dataset_id)
                .order_by(EvalCase.created_at, EvalCase.id)
            )
        ).all()
    )
    return [_case_response(case) for case in cases]


@router.patch("/cases/{case_id}", response_model=EvalCaseResponse)
async def review_eval_case(
    case_id: UUID,
    request: ReviewCaseRequest,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalCaseResponse:
    case = await session.get(EvalCase, case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Evaluation case was not found")
    await _owned_dataset(session, case.dataset_id, current_user_id)
    reviewed = await review_case(
        session,
        case_id=case_id,
        is_active=request.is_active,
        review_note=request.review_note,
    )
    await session.commit()
    return _case_response(reviewed)


@router.post("/runs", response_model=EvalRunAccepted, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_eval_run(
    request: EvalRunCreateRequest,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalRunAccepted:
    try:
        run = await create_eval_run(
            session,
            user_id=current_user_id,
            dataset_id=request.dataset_id,
            config_overrides=request.config_overrides,
        )
        await session.commit()
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    try:
        redis = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        try:
            await redis.enqueue_job("evaluate_run", str(run.id), _job_id=f"eval-run:{run.id}")
        finally:
            await redis.aclose()
    except Exception as error:
        from app.evaluation.service import fail_evaluation_run

        await fail_evaluation_run(
            session,
            run_id=run.id,
            message="evaluation job could not be queued",
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Evaluation was saved but could not be queued; retry when the worker "
                "is available."
            ),
        ) from error
    return EvalRunAccepted(run_id=run.id, status=EvalRunStatus(run.status))


@router.get("/runs", response_model=EvalRunListResponse)
async def get_eval_runs(
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> EvalRunListResponse:
    runs = await list_runs(session, user_id=current_user_id, limit=limit)
    return EvalRunListResponse(runs=[_run_response(run) for run in runs])


@router.get("/runs/{run_id}", response_model=EvalRunResponse)
async def get_eval_run(
    run_id: UUID,
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalRunResponse:
    run = await session.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Evaluation run was not found")
    if run.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="Only the run owner may view this run")
    return _run_response(run)


@router.get("/runs/{run_id}/compare", response_model=EvalCompareResponse)
async def compare_eval_runs(
    run_id: UUID,
    baseline: Annotated[UUID, Query()],
    current_user_id: Annotated[UUID, Depends(get_current_user_id)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalCompareResponse:
    try:
        comparison = await compare_runs(
            session,
            current_run_id=run_id,
            baseline_run_id=baseline,
            user_id=current_user_id,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error
    return EvalCompareResponse.model_validate(comparison)


async def _owned_dataset(session: AsyncSession, dataset_id: UUID, user_id: UUID) -> EvalDataset:
    dataset = await session.get(EvalDataset, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Evaluation dataset was not found")
    if dataset.user_id != user_id:
        raise HTTPException(status_code=403, detail="Only the dataset owner may access it")
    return dataset


async def _dataset_response(session: AsyncSession, dataset: EvalDataset) -> EvalDatasetResponse:
    stats = await refresh_dataset_case_count(session, dataset.id)
    return EvalDatasetResponse(
        id=dataset.id,
        name=dataset.name,
        version=dataset.version,
        construction_method=dataset.construction_method,
        case_count=dataset.case_count,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
        stats=DatasetStatsResponse(
            total=stats.total,
            active=stats.active,
            synthetic_total=stats.synthetic_total,
            synthetic_active=stats.synthetic_active,
            manual_active=stats.manual_active,
            synthetic_retention_rate=stats.synthetic_retention_rate,
        ),
    )


def _case_response(case: EvalCase) -> EvalCaseResponse:
    return EvalCaseResponse(
        id=case.id,
        dataset_id=case.dataset_id,
        query=case.query,
        expected_chunk_ids=[UUID(chunk_id) for chunk_id in case.expected_chunk_ids],
        source=EvalCaseSource(case.source),
        is_active=case.is_active,
        review_note=case.review_note,
        created_at=case.created_at,
    )


def _run_response(run: EvalRun) -> EvalRunResponse:
    return EvalRunResponse(
        id=run.id,
        dataset_id=run.dataset_id,
        status=EvalRunStatus(run.status),
        config_snapshot=run.config_snapshot,
        started_at=run.started_at,
        finished_at=run.finished_at,
        summary_metrics=run.summary_metrics,
        error_message=run.error_message,
        created_at=run.created_at,
    )
