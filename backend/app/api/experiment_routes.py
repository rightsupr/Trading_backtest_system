from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field, StrictBool

from app.database.experiments import Experiments
from app.models.schemas_base import StrictModel

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


class FavoriteRequest(StrictModel):
    is_favorite: StrictBool


class DeleteRequest(StrictModel):
    run_ids: list[str] = Field(min_length=1, max_length=100)


@router.get("")
def list_experiments(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    favorites: bool = False,
):
    return Experiments(request.app.state.repo).list(page, page_size, favorites)


@router.post("/delete")
def delete_experiments(body: DeleteRequest, request: Request):
    return Experiments(request.app.state.repo).delete(body.run_ids)


@router.post("/{run_id}/favorite")
def favorite_experiment(run_id: str, body: FavoriteRequest, request: Request):
    result = Experiments(request.app.state.repo).favorite(run_id, body.is_favorite)
    if result is None:
        raise HTTPException(404, "实验记录不存在")
    return result
