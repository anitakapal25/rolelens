"""FastAPI dependencies: hand route handlers the shared Services bundle."""

from typing import Annotated

from fastapi import Depends, Request

from app.services import Services


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


ServicesDep = Annotated[Services, Depends(get_services)]
