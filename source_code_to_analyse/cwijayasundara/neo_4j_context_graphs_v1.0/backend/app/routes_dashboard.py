"""Dashboard API routes — spending summary, trends, category breakdown."""

from fastapi import APIRouter, Query

from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
_service: DashboardService | None = None


def init_dashboard_service(service: DashboardService):
    global _service
    _service = service


@router.get("/summary")
def dashboard_summary(period: str | None = Query(None)):
    return _service.get_summary(period)


@router.get("/trends")
def spending_trends(
    months: int = Query(6), category: str | None = Query(None)
):
    return _service.get_trends(months, category)


@router.get("/categories")
def category_breakdown(
    period: str | None = Query(None),
    account_id: str | None = Query(None),
):
    return _service.get_categories(period, account_id)
