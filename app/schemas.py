from datetime import date, time
from typing import Literal
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
    expected_revision: int = Field(ge=1)


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
    expected_revision: int = Field(ge=1)


class GoogleAccessIn(BaseModel):
    client_id: str | None = Field(default=None, max_length=300)
    expected_revision: int = Field(ge=1)


class QuoteRulesIn(BaseModel):
    expected_revision: int = Field(ge=1)
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
    audience: Literal["TODOS", "TELEFONISTAS", "PLANIFICADORES"] = "TODOS"
    detail: str = Field(min_length=2, max_length=4000)
    communicated_by: str = Field(default="", max_length=120)
    managed_by: str | None = Field(default=None, max_length=120)
    status: Literal["PENDIENTE"] = "PENDIENTE"
    comments: str | None = Field(default=None, max_length=4000)
    allow_duplicate: bool = False

class DelayIn(BaseModel):
    service: str = Field(default="TODAS", max_length=40)
    department: str = Field(min_length=2, max_length=80)
    zone: str = Field(min_length=2, max_length=500)
    message: str = Field(default="Margen de", max_length=100)
    minutes: int | None = Field(default=None, ge=0, le=1440)
    minutes_min: int | None = Field(default=None, ge=1, le=1440, strict=True)
    minutes_max: int | None = Field(default=None, ge=1, le=1440, strict=True)
    instruction_text: str | None = Field(default=None, max_length=500)
    status: str = Field(default="VIGENTE", max_length=40)
    agent: str = Field(default="", max_length=120)
    review_minutes: int = Field(default=120, ge=15, le=1440)
    duration_minutes: int | None = Field(default=None, ge=30, le=240)
    catalog_zone: bool = False


class DelayNormalizeIn(BaseModel):
    expected_revision: int = Field(ge=1)
    status: Literal["NORMALIZADO"] = "NORMALIZADO"
    resolution_note: str | None = Field(default=None, max_length=500)


class DelayVerifyIn(BaseModel):
    expected_revision: int = Field(ge=1)
    review_minutes: int = Field(default=120, ge=15, le=1440)
    verification_note: str = Field(min_length=2, max_length=500)


class ArrivalStandardIn(BaseModel):
    department: str = Field(min_length=2, max_length=80)
    zone: str = Field(min_length=2, max_length=500)
    service: str = Field(min_length=2, max_length=40)
    minutes_min: int | None = Field(default=None, ge=1, le=1440)
    minutes_max: int | None = Field(default=None, ge=1, le=1440)
    note: str | None = Field(default=None, max_length=500)
    status: Literal["CONFIRMADO", "PROVISIONAL", "SIN_REFERENCIA"] = "PROVISIONAL"
    source: str | None = Field(default=None, max_length=500)
    owner: str = Field(default="Supervisión", min_length=2, max_length=120)
    review_interval_days: int = Field(default=90, ge=1, le=365)
    effective_from: date | None = None
    review_due_at: date | None = None
    active: bool = True


class StandardDecisionIn(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    note: str = Field(min_length=2, max_length=500)


class ZoneCoverageIn(BaseModel):
    department: str = Field(min_length=2, max_length=80)
    name: str = Field(min_length=2, max_length=200)
    owner: str = Field(default="Supervisión", min_length=2, max_length=120)
    expected_services: list[Literal["GRÚA", "ML", "SINIESTROS"]] = Field(default_factory=list)

class TransferIn(BaseModel):
    task_number: str = Field(min_length=1, max_length=120)
    transfer_type: str = Field(min_length=2, max_length=80)
    scheduled_date: date
    scheduled_time: time | None = None
    origin: str = Field(min_length=2, max_length=500)
    destination: str = Field(min_length=2, max_length=500)
    provider: str | None = Field(default=None, max_length=200)
    responsible: str | None = Field(default=None, max_length=120)
    planner: str = Field(default="", max_length=120)
    status: Literal["SIN_ASIGNAR"] = "SIN_ASIGNAR"
    comments: str | None = Field(default=None, max_length=4000)
    allow_duplicate: bool = False

class TransferEdit(BaseModel):
    expected_revision: int = Field(ge=1)
    task_number: str = Field(min_length=1, max_length=120)
    transfer_type: str = Field(min_length=2, max_length=80)
    scheduled_date: date
    scheduled_time: time | None = None
    origin: str = Field(min_length=2, max_length=500)
    destination: str = Field(min_length=2, max_length=500)
    provider: str | None = Field(default=None, max_length=200)
    responsible: str | None = Field(default=None, max_length=120)
    comments: str | None = Field(default=None, max_length=4000)
    allow_duplicate: bool = False


class TransferStatusIn(BaseModel):
    expected_revision: int = Field(ge=1)
    status: Literal["SIN_ASIGNAR", "ASIGNADO", "EN_CURSO", "FINALIZADO", "CANCELADO"]
    provider: str | None = Field(default=None, max_length=200)
    responsible: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=1000)

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

class NoticeUpdateIn(BaseModel):
    expected_revision: int = Field(ge=1)
    status: str | None = Field(default=None, max_length=40)
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
    manual_region_points: list[str] = Field(default_factory=list, max_length=3)
    include_mobile: bool = False
    include_tolls: bool = False
    uninsured: bool = False
    special: bool = False
    gavilan: bool = False
    manual_distance: bool = False


class TollIn(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1)
    name: str = Field(min_length=2, max_length=120)
    latitude: float = Field(ge=-35.5, le=-29.0)
    longitude: float = Field(ge=-59.5, le=-52.0)
    price: float | None = Field(default=None, ge=0, le=1_000_000_000)
    active: bool = True
