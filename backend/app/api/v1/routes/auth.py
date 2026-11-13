from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.security import auth_rate_limiter
from app.db.session import get_db
from app.models.identity import Profile
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    TokenRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
)
from app.services.audit import record_audit
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _limit(request: Request) -> None:
    host = request.client.host if request.client else "unknown"
    auth_rate_limiter.check(host)


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/register", response_model=RegisterResponse, status_code=201)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)) -> RegisterResponse:
    _limit(request)
    user, dev_token = AuthService(db).register(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        ip_address=_ip(request),
    )
    return RegisterResponse(
        user=user,
        message="Account created. Verify your email before signing in.",
        dev_verification_token=dev_token,
    )


@router.post("/verify-email", response_model=TokenResponse)
def verify_email(body: TokenRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    _limit(request)
    access_token, user = AuthService(db).verify_email(body.token)
    return TokenResponse(access_token=access_token, user=user)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    _limit(request)
    access_token, user = AuthService(db).login(email=body.email, password=body.password, ip_address=_ip(request))
    return TokenResponse(access_token=access_token, user=user)


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(body: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    _limit(request)
    dev_token = AuthService(db).forgot_password(body.email)
    return MessageResponse(
        message="If an account exists for that email, a reset link is ready.",
        dev_token=dev_token,
    )


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(body: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)) -> MessageResponse:
    _limit(request)
    AuthService(db).reset_password(token=body.token, password=body.password)
    return MessageResponse(message="Password updated. You can sign in.")


@router.get("/me", response_model=UserResponse)
def me(user: Profile = Depends(get_current_user), db: Session = Depends(get_db)) -> UserResponse:
    return AuthService(db).to_response(user)


@router.patch("/me", response_model=UserResponse)
def update_me(
    body: UpdateProfileRequest,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    return AuthService(db).update_profile(user, body.full_name)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    record_audit(
        db,
        action="auth.logout",
        resource_type="profile",
        actor_id=user.id,
        resource_id=user.id,
        ip_address=_ip(request),
    )
    return Response(status_code=204)
