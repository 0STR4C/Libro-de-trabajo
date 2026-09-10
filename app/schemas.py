from datetime import date, time
from pydantic import BaseModel, Field, field_validator


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=1024)


class GoogleLoginIn(BaseModel):
    credential: str = Field(min_length=1, max_length=8192)
    nonce: str = Field(min_length=1, max_length=256)


class RoleCreateIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)


class PermissionsIn(BaseModel):
    permissions: list[str] = Field(default_factory=list, max_length=100)


class UserCreateIn(BaseModel):
    display_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    username: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=1024)
    role_id: int = Field(gt=0)

    @field_validator("password")
    @classmethod
    def validate_optional_password(cls, value):
        if value in (None, ""):
            return None
        if len(value) < 12:
            raise ValueError("La contraseña debe tener al menos 12 caracteres")
        return value


class UserUpdateIn(UserCreateIn):
    active: bool = True


class GoogleAccessIn(BaseModel):
    client_id: str | None = Field(default=None, max_length=300)


class QuoteRulesIn(BaseModel):
    insured_base: float = Field(ge=0, le=1_000_000_000)
    uninsured_base: float = Field(ge=0, le=1_000_000_000)
    special_insured_base: float = Field(ge=0, le=1_000_000_000)
    special_uninsured_base: float = Field(ge=0, le=1_000_000_000)
    gavilan_base: float = Field(ge=0, le=1_000_000_000)
    included_km: float = Field(ge=0, le=1_000_000)
    extra_km_rate: float = Field(ge=0, le=1_000_000)
    special_extra_km_rate: float = Field(ge=0, le=1_000_000)
    gavilan_insured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    gavilan_uninsured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    transfer_insured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    transfer_uninsured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    transfer_special_insured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    transfer_special_uninsured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    locksmith_mvd_insured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    locksmith_mvd_uninsured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    locksmith_coast_insured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    locksmith_coast_uninsured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    locksmith_mvd_after22_insured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    locksmith_mvd_after22_uninsured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    locksmith_coast_after22_insured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    locksmith_coast_after22_uninsured_base: float | None = Field(default=None, ge=0, le=1_000_000_000)
    extra_km_insured_rate: float | None = Field(default=None, ge=0, le=1_000_000)
    extra_km_uninsured_rate: float | None = Field(default=None, ge=0, le=1_000_000)
    special_extra_km_insured_rate: float | None = Field(default=None, ge=0, le=1_000_000)
    special_extra_km_uninsured_rate: float | None = Field(default=None, ge=0, le=1_000_000)
    toll_insured: float | None = Field(default=None, ge=0, le=1_000_000_000)
    toll_uninsured: float | None = Field(default=None, ge=0, le=1_000_000_000)
    waiting_hour_insured: float | None = Field(default=None, ge=0, le=1_000_000_000)
    waiting_hour_uninsured: float | None = Field(default=None, ge=0, le=1_000_000_000)
    rescue_hour_insured: float | None = Field(default=None, ge=0, le=1_000_000_000)
    rescue_hour_uninsured: float | None = Field(default=None, ge=0, le=1_000_000_000)

class NoticeIn(BaseModel):
    task_number: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=80)
    notice_type: str = Field(min_length=2, max_length=120)
    audience: str = Field(default="TODOS", max_length=40)
    detail: str = Field(min_length=2, max_length=4000)
    communicated_by: str = Field(default="", max_length=120)
    managed_by: str | None = Field(default=None, max_length=120)
    status: str = Field(default="PENDIENTE", max_length=40)
    comments: str | None = Field(default=None, max_length=4000)

class DelayIn(BaseModel):
    service: str = Field(default="TODAS", max_length=40)
    department: str = Field(min_length=2, max_length=80)
    zone: str = Field(min_length=2, max_length=500)
    message: str = Field(default="Margen de", max_length=100)
    minutes: int | None = Field(default=None, ge=0, le=1440)
    status: str = Field(default="VIGENTE", max_length=40)
    agent: str = Field(default="", max_length=120)

class TransferIn(BaseModel):
    task_number: str = Field(min_length=1, max_length=120)
    transfer_type: str = Field(min_length=2, max_length=80)
    scheduled_date: date
    scheduled_time: time | None = None
    origin: str = Field(min_length=2, max_length=500)
    destination: str = Field(min_length=2, max_length=500)
    provider: str | None = Field(default=None, max_length=200)
    planner: str = Field(default="", max_length=120)
    status: str = Field(default="PENDIENTE", max_length=40)
    comments: str | None = Field(default=None, max_length=4000)

class TransferEdit(BaseModel):
    task_number: str
    transfer_type: str
    scheduled_date: date
    scheduled_time: time | None = None
    origin: str
    destination: str
    provider: str | None = None
    comments: str | None = None

class ScheduleIn(BaseModel):
    user_id: int = Field(gt=0)
    schedule_date: date
    shift_name: str = Field(min_length=2, max_length=80)
    start_time: time | None = None
    end_time: time | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ScheduleCopyIn(BaseModel):
    source_week: date
    target_week: date
    employee_id: int | None = Field(default=None, gt=0)
    role: str | None = Field(default=None, max_length=80)

class StatusIn(BaseModel):
    status: str = Field(min_length=1, max_length=40)
    actor: str = Field(default="Operador", max_length=120)
    managed_by: str | None = Field(default=None, max_length=120)
    comments: str | None = Field(default=None, max_length=4000)


class QuoteIn(BaseModel):
    task_number: str | None = Field(default=None, max_length=120)
    origin: str | None = Field(default=None, max_length=1000)
    destination: str | None = Field(default=None, max_length=1000)
    mobile_origin: str | None = Field(default=None, max_length=1000)
    manual_trip_km: float | None = Field(default=None, ge=0, le=1_000_000)
    manual_mobile_km: float | None = Field(default=None, ge=0, le=1_000_000)
    manual_toll_count: int | None = Field(default=None, ge=0, le=100)
    include_mobile: bool = False
    include_tolls: bool = False
    uninsured: bool = False
    special: bool = False
    gavilan: bool = False
    manual_distance: bool = False


class TollIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    latitude: float = Field(ge=-35.5, le=-29.0)
    longitude: float = Field(ge=-59.5, le=-52.0)
    price: float | None = Field(default=None, ge=0, le=1_000_000_000)
    active: bool = True
