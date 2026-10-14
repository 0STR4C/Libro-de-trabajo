"""CRUD paginado de tiempos base de arribo para PostgreSQL."""

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Body, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from .arrival_times import arrival_catalog, clean_arrival_location, clean_arrival_time
from .delays import STANDARD_SERVICES, normalized_key
from .geography import URUGUAY_ZONES


class ArrivalTimeIn(BaseModel):
    expected_revision: int | None = Field(default=None, ge=1, strict=True)
    service: str = Field(min_length=2, max_length=40)
    department: str = Field(min_length=2, max_length=80)
    zone: str = Field(min_length=2, max_length=120)
    base_estimated_minutes: int = Field(ge=1, le=1440, strict=True)
    is_active: bool = Field(default=True, strict=True)


def _filter_value(value: str, choices, label: str) -> str | None:
    if not value:
        return None
    selected = next((item for item in choices if normalized_key(item) == normalized_key(value)), None)
    if selected is None:
        raise HTTPException(422, f"{label} inválido")
    return selected


def register_arrival_times_routes(app, connect, authorized, audit, now) -> None:
    router = APIRouter(prefix="/api/arrival-times", tags=["Tiempos de arribo"])

    @router.get("")
    def list_arrival_times(
        request: Request,
        department: str = "",
        service: str = "",
        is_active: bool | None = None,
        limit: int = Query(50, ge=1, le=50),
        offset: int = Query(0, ge=0),
    ):
        authorized(request, "standards.view")
        selected_department = _filter_value(department, URUGUAY_ZONES, "Departamento")
        selected_service = _filter_value(service, STANDARD_SERVICES, "Servicio")
        conditions = []
        values = []
        if selected_department:
            conditions.append("department=%s")
            values.append(selected_department)
        if selected_service:
            conditions.append("service=%s")
            values.append(selected_service)
        if is_active is not None:
            conditions.append("is_active=%s")
            values.append(is_active)
        where = " AND ".join(conditions) or "TRUE"
        with connect() as database:
            total = database.execute(f"SELECT count(*) AS total FROM arrival_times WHERE {where}", values).fetchone()["total"]
            items = database.execute(
                f"SELECT * FROM arrival_times WHERE {where} ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s",
                (*values, limit, offset),
            ).fetchall()
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    @router.get("/geography")
    def geography(request: Request):
        authorized(request, "standards.view")
        return arrival_catalog()

    @router.get("/match")
    def matching_arrival_time(request: Request, service: str, department: str, zone: str):
        authorized(request, "standards.view")
        try:
            key = clean_arrival_location(service, department, zone)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        with connect() as database:
            item = database.execute(
                """SELECT * FROM arrival_times WHERE service=%s AND department=%s
                   AND zone=%s AND is_active=TRUE""", key,
            ).fetchone()
        if not item:
            raise HTTPException(404, "No hay un tiempo activo para esa combinación")
        return item

    @router.get("/{item_id}")
    def get_arrival_time(item_id: int, request: Request):
        authorized(request, "standards.view")
        with connect() as database:
            item = database.execute("SELECT * FROM arrival_times WHERE id=%s", (item_id,)).fetchone()
        if not item:
            raise HTTPException(404, "Tiempo de arribo inexistente")
        return item

    @router.post("", status_code=201)
    def create_arrival_time(request: Request, data: ArrivalTimeIn = Body(...)):
        actor = authorized(request, "arrival_times.manage")
        try:
            item = clean_arrival_time(data.model_dump())
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        stamp = now()
        try:
            with connect() as database:
                created = database.execute(
                    """INSERT INTO arrival_times(service,department,zone,base_estimated_minutes,
                           is_active,created_by,updated_by,created_at,updated_at)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (item["service"], item["department"], item["zone"], item["base_estimated_minutes"],
                     item["is_active"], actor["display_name"], actor["display_name"], stamp, stamp),
                ).fetchone()
                audit(database, "arrival_time", created["id"], "CREADO", actor["display_name"],
                      f"{item['department']} · {item['service']} · {item['zone']}",
                      actor_id=actor["id"], after=created)
        except psycopg.errors.UniqueViolation as error:
            raise HTTPException(409, "Ya existe un tiempo activo para ese servicio y zona") from error
        return created

    @router.put("/{item_id}")
    @router.patch("/{item_id}")
    def update_arrival_time(item_id: int, request: Request, data: ArrivalTimeIn = Body(...)):
        if data.expected_revision is None:
            raise HTTPException(422, "Indique la revisión del tiempo de arribo")
        actor = authorized(request, "arrival_times.manage")
        try:
            item = clean_arrival_time(data.model_dump())
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        try:
            with connect() as database:
                previous = database.execute("SELECT * FROM arrival_times WHERE id=%s FOR UPDATE", (item_id,)).fetchone()
                if not previous:
                    raise HTTPException(404, "Tiempo de arribo inexistente")
                if previous["revision"] != data.expected_revision:
                    raise HTTPException(409, "El tiempo de arribo cambió. Recargá el registro antes de guardar")
                updated = database.execute(
                    """UPDATE arrival_times SET service=%s,department=%s,zone=%s,
                           base_estimated_minutes=%s,is_active=%s,updated_by=%s,updated_at=%s,revision=revision+1
                       WHERE id=%s RETURNING *""",
                    (item["service"], item["department"], item["zone"], item["base_estimated_minutes"],
                     item["is_active"], actor["display_name"], now(), item_id),
                ).fetchone()
                action = ("REACTIVADO" if item["is_active"] else "DESACTIVADO") if item["is_active"] != previous["is_active"] else "ACTUALIZADO"
                audit(database, "arrival_time", item_id, action, actor["display_name"],
                      f"{item['department']} · {item['service']} · {item['zone']}",
                      actor_id=actor["id"], before=previous, after=updated)
        except psycopg.errors.UniqueViolation as error:
            raise HTTPException(409, "Ya existe un tiempo activo para ese servicio y zona") from error
        return updated

    @router.delete("/{item_id}", status_code=204)
    def deactivate_arrival_time(item_id: int, request: Request, expected_revision: int = Query(..., ge=1)):
        actor = authorized(request, "arrival_times.manage")
        with connect() as database:
            previous = database.execute("SELECT * FROM arrival_times WHERE id=%s FOR UPDATE", (item_id,)).fetchone()
            if not previous:
                raise HTTPException(404, "Tiempo de arribo inexistente")
            if previous["revision"] != expected_revision:
                raise HTTPException(409, "El tiempo de arribo cambió. Recargá el registro antes de desactivar")
            if previous["is_active"]:
                updated = database.execute(
                    "UPDATE arrival_times SET is_active=FALSE,updated_by=%s,updated_at=%s,revision=revision+1 WHERE id=%s RETURNING *",
                    (actor["display_name"], now(), item_id),
                ).fetchone()
                audit(database, "arrival_time", item_id, "DESACTIVADO", actor["display_name"],
                      f"{previous['department']} · {previous['service']} · {previous['zone']}",
                      actor_id=actor["id"], before=previous, after=updated)
        return Response(status_code=204)

    app.include_router(router)
