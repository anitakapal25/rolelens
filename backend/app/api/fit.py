"""Fit dashboard routes."""

from fastapi import APIRouter, HTTPException, status

from app.api.deps import ServicesDep
from app.fit.service import DocumentNotFound, NoResume, NotAJob, fit_for_all, fit_for_job
from app.models import ErrorResponse, FitReport

router = APIRouter(prefix="/fit", tags=["fit"])

ERRORS = {404: {"model": ErrorResponse}, 409: {"model": ErrorResponse},
          502: {"model": ErrorResponse}, 503: {"model": ErrorResponse}}


@router.get("", responses=ERRORS)
def all_fits(svc: ServicesDep) -> list[FitReport]:
    try:
        return fit_for_all(svc)
    except NoResume as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/{job_id}", responses=ERRORS)
def job_fit(job_id: str, svc: ServicesDep) -> FitReport:
    try:
        return fit_for_job(svc, job_id)
    except NoResume as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except (DocumentNotFound, NotAJob) as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found.") from exc
