from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings


def get_app_settings() -> Settings:
    return get_settings()


def verify_token(
    settings: Settings = Depends(get_app_settings),
    x_api_token: str | None = Header(None, convert_underscores=False),
) -> None:
    expected = settings.api_token
    if not expected:
        return
    if x_api_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-TOKEN",
        )

