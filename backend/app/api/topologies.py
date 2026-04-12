"""Topology management API routes."""

import json
from typing import Any

from fastapi import APIRouter, Query, UploadFile, File
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError, ERROR_NOT_FOUND
from app.core.service_registry import registry
from app.dal.base import DAL
from app.models.response import success, paged
from app.models.topology import (
    DeviceCreate, DeviceUpdate, LinkCreate, AlarmCreate, MetricCreate,
    TopologyCreate, TopologyUpdate, LayoutRequest, PortGenerateConfig,
)
from app.services.topology_manager import TopologyManager

router = APIRouter(prefix="/api/topologies", tags=["拓扑管理"])


def _get_dal() -> DAL:
    return registry.get("dal")


def _get_topo() -> TopologyManager:
    return registry.get("topology_manager")


# ==================================================================
# Topology CRUD
# ==================================================================

@router.get("")
async def list_topologies(keyword: str | None = None):
    dal = _get_dal()
    topos = await dal.list_topologies()
    if keyword:
        kw = keyword.lower()
        topos = [t for t in topos if kw in t.get("name", "").lower()]
    return success({"items": topos, "total": len(topos)})


@router.post("")
async def create_topology(req: TopologyCreate):
    dal = _get_dal()
    topo_mgr = _get_topo()
    import uuid
    topo_id = f"topo_{uuid.uuid4().hex[:8]}"
    data = topo_mgr.serialize()  # empty data for new topo
    result = await dal.save_topology(topo_id, req.name, req.description, data)
    return success(result)


@router.get("/{topologyId}")
async def get_topology(topologyId: str):
    dal = _get_dal()
    topo = await dal.get_topology(topologyId)
    if topo is None:
        raise AppError(ERROR_NOT_FOUND, f"拓扑 '{topologyId}' 不存在", status_code=404)
    topo_data = dict(topo)
    if isinstance(topo_data.get("data"), str):
        topo_data["data"] = json.loads(topo_data["data"])
    return success(topo_data)


@router.put("/{topologyId}")
async def update_topology(topologyId: str, req: TopologyUpdate):
    dal = _get_dal()
    topo = await dal.get_topology(topologyId)
    if topo is None:
        raise AppError(ERROR_NOT_FOUND, f"拓扑 '{topologyId}' 不存在", status_code=404)
    name = req.name if req.name is not None else topo["name"]
    desc = req.description if req.description is not None else topo["description"]
    data = json.loads(topo["data"]) if isinstance(topo["data"], str) else topo["data"]
    result = await dal.save_topology(topologyId, name, desc, data, is_active=bool(topo["is_active"]))
    return success(result)


@router.delete("/{topologyId}")
async def delete_topology(topologyId: str):
    dal = _get_dal()
    deleted = await dal.delete_topology(topologyId)
    if not deleted:
        raise AppError(ERROR_NOT_FOUND, f"拓扑 '{topologyId}' 不存在", status_code=404)
    return success()


# ==================================================================
# Save / Load / Versions
# ==================================================================

@router.post("/{topologyId}/save")
async def save_topology(topologyId: str):
    dal = _get_dal()
    topo_mgr = _get_topo()
    topo = await dal.get_topology(topologyId)
    if topo is None:
        raise AppError(ERROR_NOT_FOUND, f"拓扑 '{topologyId}' 不存在", status_code=404)
    data = topo_mgr.serialize()
    result = await dal.save_topology(topologyId, topo["name"], topo["description"], data, is_active=True)
    topo_mgr._dirty = False
    # Cleanup old versions
    await dal.cleanup_history(topologyId)
    return success(result)


@router.post("/{topologyId}/load")
async def load_topology(topologyId: str):
    dal = _get_dal()
    topo_mgr = _get_topo()
    topo = await dal.load_topology(topologyId)
    if topo is None:
        raise AppError(ERROR_NOT_FOUND, f"拓扑 '{topologyId}' 不存在", status_code=404)
    data = json.loads(topo["data"]) if isinstance(topo["data"], str) else topo["data"]
    topo_mgr.load_data(data)
    return success({"id": topologyId, "version": topo["version"], "stats": topo_mgr.stats()})


@router.get("/{topologyId}/versions")
async def list_versions(topologyId: str):
    dal = _get_dal()
    history = await dal.list_history(topologyId)
    return success({"items": history, "total": len(history)})


@router.post("/{topologyId}/versions/{version}/restore")
async def restore_version(topologyId: str, version: int):
    dal = _get_dal()
    topo_mgr = _get_topo()
    result = await dal.restore_version(topologyId, version)
    if result is None:
        raise AppError(ERROR_NOT_FOUND, "版本不存在", status_code=404)
    topo = await dal.get_topology(topologyId)
    data = json.loads(topo["data"]) if isinstance(topo["data"], str) else topo["data"]
    topo_mgr.load_data(data)
    return success(result)


# ==================================================================
# Import / Export
# ==================================================================

@router.get("/{topologyId}/export")
async def export_topology(topologyId: str):
    dal = _get_dal()
    topo = await dal.get_topology(topologyId)
    if topo is None:
        raise AppError(ERROR_NOT_FOUND, f"拓扑 '{topologyId}' 不存在", status_code=404)
    data = json.loads(topo["data"]) if isinstance(topo["data"], str) else topo["data"]
    export_data = {"name": topo["name"], "description": topo["description"], "data": data}
    return JSONResponse(content=export_data, headers={
        "Content-Disposition": f'attachment; filename="{topo["name"]}.json"'
    })


@router.post("/import")
async def import_topology(file: UploadFile = File(...)):
    dal = _get_dal()
    topo_mgr = _get_topo()
    content = await file.read()
    try:
        import_data = json.loads(content)
    except json.JSONDecodeError:
        raise AppError(10001, "JSON 格式无效", status_code=400)

    import uuid
    topo_id = f"topo_{uuid.uuid4().hex[:8]}"
    name = import_data.get("name", file.filename or "导入的拓扑")
    desc = import_data.get("description", "")
    data = import_data.get("data", import_data)  # support both wrapped and raw format
    result = await dal.save_topology(topo_id, name, desc, data)
    return success(result)


# ==================================================================
# Validate / Fix / Layout
# ==================================================================

@router.post("/{topologyId}/validate")
async def validate_topology(topologyId: str):
    topo_mgr = _get_topo()
    issues = topo_mgr.validate()
    stats = topo_mgr.stats()
    return success({
        "stats": stats,
        "issues": [i.model_dump() for i in issues],
        "errorCount": sum(1 for i in issues if i.level == "error"),
        "warningCount": sum(1 for i in issues if i.level == "warning"),
    })


@router.post("/{topologyId}/validate/fix")
async def fix_topology(topologyId: str):
    topo_mgr = _get_topo()
    fixes = await topo_mgr.fix_issues()
    issues_after = topo_mgr.validate()
    return success({
        "fixes": fixes,
        "remainingIssues": [i.model_dump() for i in issues_after],
    })


@router.post("/{topologyId}/layout")
async def layout_topology(topologyId: str, req: LayoutRequest):
    topo_mgr = _get_topo()
    positions = topo_mgr.compute_layout(req.algorithm, req.options)
    topo_mgr.update_canvas({"nodePositions": positions})
    return success({"nodePositions": positions})


# ==================================================================
# Canvas
# ==================================================================

@router.put("/{topologyId}/canvas")
async def update_canvas(topologyId: str, body: dict):
    topo_mgr = _get_topo()
    canvas = topo_mgr.update_canvas(body)
    return success(canvas.model_dump())


# ==================================================================
# Devices
# ==================================================================

@router.get("/{topologyId}/devices")
async def list_devices(
    topologyId: str,
    type: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=1000),
):
    topo_mgr = _get_topo()
    devices = topo_mgr.list_devices(type_filter=type, status_filter=status, keyword=keyword)
    total = len(devices)
    start = (pageNo - 1) * pageSize
    items = [d.model_dump() for d in devices[start:start + pageSize]]
    return paged(items, total, pageNo, pageSize)


@router.post("/{topologyId}/devices")
async def create_device(topologyId: str, req: DeviceCreate):
    topo_mgr = _get_topo()
    device = await topo_mgr.create_device(req)
    return success(device.model_dump())


@router.get("/{topologyId}/devices/{deviceId}")
async def get_device(topologyId: str, deviceId: str):
    topo_mgr = _get_topo()
    device = topo_mgr.get_device(deviceId)
    return success(device.model_dump())


@router.put("/{topologyId}/devices/{deviceId}")
async def update_device(topologyId: str, deviceId: str, req: DeviceUpdate):
    topo_mgr = _get_topo()
    device = await topo_mgr.update_device(deviceId, req)
    return success(device.model_dump())


@router.delete("/{topologyId}/devices/{deviceId}")
async def delete_device(topologyId: str, deviceId: str):
    topo_mgr = _get_topo()
    await topo_mgr.delete_device(deviceId)
    return success()


@router.put("/{topologyId}/devices/batch")
async def batch_update_devices(topologyId: str, body: dict):
    topo_mgr = _get_topo()
    updates = body.get("updates", [])
    fields = body.get("fields", {})
    ids = body.get("ids", [])
    if ids and fields:
        updates = [{"id": did, **fields} for did in ids]
    results = await topo_mgr.batch_update_devices(updates)
    return success({"updated": len(results)})


@router.delete("/{topologyId}/devices/batch")
async def batch_delete_devices(topologyId: str, body: dict):
    topo_mgr = _get_topo()
    ids = body.get("ids", [])
    count = await topo_mgr.batch_delete_devices(ids)
    return success({"deleted": count})


# ==================================================================
# Ports
# ==================================================================

@router.get("/{topologyId}/devices/{deviceId}/ports")
async def list_ports(
    topologyId: str, deviceId: str,
    status: str | None = None,
    keyword: str | None = None,
):
    topo_mgr = _get_topo()
    ports = topo_mgr.list_ports(deviceId)
    if status:
        ports = [p for p in ports if p.status == status]
    if keyword:
        kw = keyword.lower()
        ports = [p for p in ports if kw in p.name.lower() or kw in p.dn.lower()]
    return success({"items": [p.model_dump() for p in ports], "total": len(ports)})


@router.post("/{topologyId}/devices/{deviceId}/ports")
async def create_port(topologyId: str, deviceId: str, body: dict):
    topo_mgr = _get_topo()
    port = await topo_mgr.create_port(
        deviceId, name=body["name"],
        type=body.get("type", "GE"),
        speed=body.get("speed", "1Gbps"),
        dnTemplate=body.get("dnTemplate", "{deviceDn},PORT={index}"),
    )
    return success(port.model_dump())


@router.post("/{topologyId}/devices/{deviceId}/ports/generate")
async def generate_ports(topologyId: str, deviceId: str, req: PortGenerateConfig):
    topo_mgr = _get_topo()
    ports = await topo_mgr.generate_ports(deviceId, req)
    return success({"items": [p.model_dump() for p in ports], "total": len(ports)})


@router.put("/{topologyId}/ports/{portId}")
async def update_port(topologyId: str, portId: str, body: dict):
    topo_mgr = _get_topo()
    port = await topo_mgr.update_port(portId, **body)
    return success(port.model_dump())


@router.delete("/{topologyId}/ports/{portId}")
async def delete_port(topologyId: str, portId: str):
    topo_mgr = _get_topo()
    await topo_mgr.delete_port(portId)
    return success()


@router.put("/{topologyId}/devices/{deviceId}/ports/batch")
async def batch_update_ports(topologyId: str, deviceId: str, body: dict):
    topo_mgr = _get_topo()
    ids = body.get("ids", [])
    fields = body.get("fields", {})
    count = 0
    for pid in ids:
        await topo_mgr.update_port(pid, **fields)
        count += 1
    return success({"updated": count})


@router.get("/{topologyId}/devices/{deviceId}/ports/export")
async def export_ports(topologyId: str, deviceId: str):
    topo_mgr = _get_topo()
    ports = topo_mgr.list_ports(deviceId)
    return JSONResponse(content=[p.model_dump() for p in ports])


@router.post("/{topologyId}/devices/{deviceId}/ports/import")
async def import_ports(topologyId: str, deviceId: str, file: UploadFile = File(...)):
    topo_mgr = _get_topo()
    content = await file.read()
    ports_data = json.loads(content)
    created = []
    for pd in ports_data:
        port = await topo_mgr.create_port(
            deviceId, name=pd["name"],
            type=pd.get("type", "GE"),
            speed=pd.get("speed", "1Gbps"),
        )
        created.append(port)
    return success({"imported": len(created)})


# ==================================================================
# Links
# ==================================================================

@router.get("/{topologyId}/links")
async def list_links(topologyId: str):
    topo_mgr = _get_topo()
    links = topo_mgr.list_links()
    return success({"items": [l.model_dump() for l in links], "total": len(links)})


@router.post("/{topologyId}/links")
async def create_link(topologyId: str, req: LinkCreate):
    topo_mgr = _get_topo()
    link = await topo_mgr.create_link(req)
    return success(link.model_dump())


@router.put("/{topologyId}/links/{linkId}")
async def update_link(topologyId: str, linkId: str, body: dict):
    topo_mgr = _get_topo()
    link = await topo_mgr.update_link(linkId, **body)
    return success(link.model_dump())


@router.delete("/{topologyId}/links/{linkId}")
async def delete_link(topologyId: str, linkId: str):
    topo_mgr = _get_topo()
    await topo_mgr.delete_link(linkId)
    return success()


@router.delete("/{topologyId}/links/batch")
async def batch_delete_links(topologyId: str, body: dict):
    topo_mgr = _get_topo()
    ids = body.get("ids", [])
    count = await topo_mgr.batch_delete_links(ids)
    return success({"deleted": count})


# ==================================================================
# Alarms
# ==================================================================

@router.get("/{topologyId}/alarms")
async def list_alarms(
    topologyId: str,
    deviceId: str | None = None,
    level: str | None = None,
    status: str | None = None,
):
    topo_mgr = _get_topo()
    alarms = topo_mgr.list_alarms(device_id=deviceId, level=level, status=status)
    return success({"items": [a.model_dump() for a in alarms], "total": len(alarms)})


@router.post("/{topologyId}/alarms")
async def create_alarm(topologyId: str, req: AlarmCreate):
    topo_mgr = _get_topo()
    alarm = await topo_mgr.create_alarm(
        deviceId=req.deviceId, level=req.level,
        type=req.type, content=req.content, occurTime=req.occurTime,
    )
    return success(alarm.model_dump())


@router.post("/{topologyId}/alarms/{alarmId}/clear")
async def clear_alarm(topologyId: str, alarmId: str):
    topo_mgr = _get_topo()
    alarm = await topo_mgr.clear_alarm(alarmId)
    return success(alarm.model_dump())


@router.delete("/{topologyId}/alarms/{alarmId}")
async def delete_alarm(topologyId: str, alarmId: str):
    topo_mgr = _get_topo()
    await topo_mgr.delete_alarm(alarmId)
    return success()


# ==================================================================
# Metrics
# ==================================================================

@router.get("/{topologyId}/metrics")
async def list_metrics(topologyId: str, deviceId: str | None = None):
    topo_mgr = _get_topo()
    metrics = topo_mgr.list_metrics(device_id=deviceId)
    return success({"items": [m.model_dump() for m in metrics], "total": len(metrics)})


@router.post("/{topologyId}/metrics")
async def create_metric(topologyId: str, req: MetricCreate):
    topo_mgr = _get_topo()
    metric = await topo_mgr.create_metric(
        deviceId=req.deviceId, name=req.name, value=req.value,
        unit=req.unit, collectTime=req.collectTime,
        collectInterval=req.collectInterval,
    )
    return success(metric.model_dump())


@router.delete("/{topologyId}/metrics/{metricId}")
async def delete_metric(topologyId: str, metricId: str):
    topo_mgr = _get_topo()
    await topo_mgr.delete_metric(metricId)
    return success()
