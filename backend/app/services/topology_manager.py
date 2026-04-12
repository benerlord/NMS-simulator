"""Topology manager — single source of truth for in-memory topology data."""

import math
import uuid
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.core.event_bus import event_bus
from app.core.exceptions import AppError, ERROR_NOT_FOUND, ERROR_CONFLICT, ERROR_VALIDATION
from app.dal.memory_store import MemoryStore
from app.models.topology import (
    Alarm, CanvasState, Device, DeviceCreate, DeviceUpdate, Link,
    LinkCreate, Metric, Port, PortGenerateConfig, TopologyData,
    ValidationIssue,
)


def _uid(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


class TopologyManager:
    """Manages the in-memory topology graph with indices and sync."""

    def __init__(self, memory: MemoryStore) -> None:
        self._memory = memory
        self._data = TopologyData()
        # Indices
        self._devices_by_id: dict[str, Device] = {}
        self._devices_by_dn: dict[str, Device] = {}
        self._ports_by_id: dict[str, Port] = {}
        self._ports_by_device: dict[str, list[Port]] = {}
        self._links_by_id: dict[str, Link] = {}
        self._alarms_by_id: dict[str, Alarm] = {}
        self._metrics_by_id: dict[str, Metric] = {}
        self._dirty = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def dirty(self) -> bool:
        return self._dirty

    @property
    def data(self) -> TopologyData:
        return self._data

    @property
    def canvas(self) -> CanvasState:
        return self._data.canvas

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def load_data(self, data: dict | TopologyData) -> None:
        """Load full topology data (from DB) and rebuild indices."""
        if isinstance(data, dict):
            self._data = TopologyData(**data)
        else:
            self._data = data
        self._rebuild_indices()
        self._dirty = False

    def serialize(self) -> dict:
        """Serialize to dict for persistence."""
        return self._data.model_dump()

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def _rebuild_indices(self) -> None:
        self._devices_by_id.clear()
        self._devices_by_dn.clear()
        self._ports_by_id.clear()
        self._ports_by_device.clear()
        self._links_by_id.clear()
        self._alarms_by_id.clear()
        self._metrics_by_id.clear()

        for d in self._data.devices:
            self._devices_by_id[d.id] = d
            if d.dn:
                self._devices_by_dn[d.dn] = d
        for p in self._data.ports:
            self._ports_by_id[p.id] = p
            self._ports_by_device.setdefault(p.deviceId, []).append(p)
        for l in self._data.links:
            self._links_by_id[l.id] = l
        for a in self._data.alarms:
            self._alarms_by_id[a.id] = a
        for m in self._data.metrics:
            self._metrics_by_id[m.id] = m

    # ------------------------------------------------------------------
    # DN generation
    # ------------------------------------------------------------------

    @staticmethod
    def _generate_dn(template: str, **kwargs: Any) -> str:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError):
            return template

    def _compute_device_dn(self, device: Device) -> str:
        return self._generate_dn(device.dnTemplate, id=device.id, name=device.name, ip=device.ip)

    def _compute_port_dn(self, port: Port, device: Device) -> str:
        return self._generate_dn(
            port.dnTemplate,
            deviceDn=device.dn, index=port.name.split("/")[-1] if "/" in port.name else port.id,
            name=port.name, id=port.id,
        )

    # ------------------------------------------------------------------
    # Device CRUD
    # ------------------------------------------------------------------

    async def create_device(self, req: DeviceCreate) -> Device:
        dev_id = _uid("dev_")
        device = Device(
            id=dev_id,
            name=req.name,
            type=req.type,
            dnTemplate=req.dnTemplate,
            ip=req.ip,
            vendor=req.vendor,
            model=req.model,
            status=req.status,
            customFields=req.customFields,
        )
        device.dn = self._compute_device_dn(device)

        self._data.devices.append(device)
        self._devices_by_id[device.id] = device
        if device.dn:
            self._devices_by_dn[device.dn] = device

        # Auto-generate ports if config provided
        if req.portConfig:
            ports = await self.generate_ports(device.id, req.portConfig)
            device.portIds = [p.id for p in ports]

        # Canvas position
        if req.position:
            self._data.canvas.nodePositions[device.id] = req.position

        self._dirty = True
        await self._sync_device(device)
        await event_bus.emit("topology.device.created", device=device.model_dump())
        return device

    def get_device(self, device_id: str) -> Device:
        dev = self._devices_by_id.get(device_id)
        if dev is None:
            raise AppError(ERROR_NOT_FOUND, f"设备 '{device_id}' 不存在", status_code=404)
        return dev

    def get_device_by_dn(self, dn: str) -> Device | None:
        return self._devices_by_dn.get(dn)

    def list_devices(self, type_filter: str | None = None, status_filter: str | None = None,
                     keyword: str | None = None) -> list[Device]:
        result = self._data.devices
        if type_filter:
            result = [d for d in result if d.type == type_filter]
        if status_filter:
            result = [d for d in result if d.status == status_filter]
        if keyword:
            kw = keyword.lower()
            result = [d for d in result if kw in d.name.lower() or kw in d.dn.lower()]
        return result

    async def update_device(self, device_id: str, update: DeviceUpdate) -> Device:
        device = self.get_device(device_id)
        update_data = update.model_dump(exclude_none=True)
        for key, val in update_data.items():
            setattr(device, key, val)
        # Recompute DN if template changed
        if "dnTemplate" in update_data or "name" in update_data or "ip" in update_data:
            old_dn = device.dn
            device.dn = self._compute_device_dn(device)
            if old_dn in self._devices_by_dn:
                del self._devices_by_dn[old_dn]
            self._devices_by_dn[device.dn] = device

        self._dirty = True
        await self._sync_device(device)
        await event_bus.emit("topology.device.updated", device=device.model_dump())
        return device

    async def delete_device(self, device_id: str) -> None:
        device = self.get_device(device_id)

        # Delete associated links
        links_to_delete = [
            l for l in self._data.links
            if l.sourceDeviceId == device_id or l.targetDeviceId == device_id
        ]
        for link in links_to_delete:
            await self._remove_link(link)

        # Delete associated ports
        ports = self._ports_by_device.pop(device_id, [])
        for port in ports:
            self._data.ports.remove(port)
            del self._ports_by_id[port.id]
            await self._memory.delete_row("ports", port.id)

        # Delete associated alarms and metrics
        alarms_to_del = [a for a in self._data.alarms if a.deviceId == device_id]
        for a in alarms_to_del:
            self._data.alarms.remove(a)
            del self._alarms_by_id[a.id]
            await self._memory.delete_row("alarms", a.id)

        metrics_to_del = [m for m in self._data.metrics if m.deviceId == device_id]
        for m in metrics_to_del:
            self._data.metrics.remove(m)
            del self._metrics_by_id[m.id]
            await self._memory.delete_row("metrics", m.id)

        # Delete device itself
        self._data.devices.remove(device)
        del self._devices_by_id[device_id]
        if device.dn in self._devices_by_dn:
            del self._devices_by_dn[device.dn]
        self._data.canvas.nodePositions.pop(device_id, None)
        await self._memory.delete_row("devices", device_id)

        self._dirty = True
        await event_bus.emit("topology.device.deleted", deviceId=device_id)

    async def batch_update_devices(self, updates: list[dict]) -> list[Device]:
        """Batch update devices. Each dict must have 'id' and fields to update."""
        results = []
        for u in updates:
            dev_id = u.pop("id")
            dev = await self.update_device(dev_id, DeviceUpdate(**u))
            results.append(dev)
        return results

    async def batch_delete_devices(self, device_ids: list[str]) -> int:
        count = 0
        for did in device_ids:
            if did in self._devices_by_id:
                await self.delete_device(did)
                count += 1
        return count

    # ------------------------------------------------------------------
    # Port CRUD
    # ------------------------------------------------------------------

    async def generate_ports(self, device_id: str, config: PortGenerateConfig) -> list[Port]:
        device = self.get_device(device_id)
        ports = []
        for i in range(config.count):
            idx = config.startIndex + i
            port_id = _uid("port_")
            port = Port(
                id=port_id,
                deviceId=device_id,
                name=f"{config.prefix}{idx}",
                dnTemplate=config.dnTemplate,
                type=config.type,
                speed=config.speed,
                status="free",
            )
            port.dn = self._compute_port_dn(port, device)
            ports.append(port)
            self._data.ports.append(port)
            self._ports_by_id[port.id] = port
            self._ports_by_device.setdefault(device_id, []).append(port)
            await self._sync_port(port)

        device.portIds = [p.id for p in self._ports_by_device.get(device_id, [])]
        await self._sync_device(device)
        self._dirty = True
        await event_bus.emit("topology.ports.generated", deviceId=device_id, count=config.count)
        return ports

    async def create_port(self, device_id: str, name: str, type: str = "GE",
                          speed: str = "1Gbps", dnTemplate: str = "{deviceDn},PORT={index}") -> Port:
        device = self.get_device(device_id)
        port = Port(
            id=_uid("port_"),
            deviceId=device_id,
            name=name,
            dnTemplate=dnTemplate,
            type=type,
            speed=speed,
        )
        port.dn = self._compute_port_dn(port, device)
        self._data.ports.append(port)
        self._ports_by_id[port.id] = port
        self._ports_by_device.setdefault(device_id, []).append(port)
        device.portIds.append(port.id)
        await self._sync_port(port)
        await self._sync_device(device)
        self._dirty = True
        return port

    async def update_port(self, port_id: str, **kwargs: Any) -> Port:
        port = self._ports_by_id.get(port_id)
        if port is None:
            raise AppError(ERROR_NOT_FOUND, f"端口 '{port_id}' 不存在", status_code=404)
        for k, v in kwargs.items():
            if v is not None and hasattr(port, k):
                setattr(port, k, v)
        device = self._devices_by_id.get(port.deviceId)
        if device:
            port.dn = self._compute_port_dn(port, device)
        await self._sync_port(port)
        self._dirty = True
        return port

    async def delete_port(self, port_id: str) -> None:
        port = self._ports_by_id.get(port_id)
        if port is None:
            raise AppError(ERROR_NOT_FOUND, f"端口 '{port_id}' 不存在", status_code=404)
        # Remove links using this port
        links_to_del = [l for l in self._data.links
                        if l.sourcePortId == port_id or l.targetPortId == port_id]
        for link in links_to_del:
            await self._remove_link(link)
        # Remove port
        self._data.ports.remove(port)
        del self._ports_by_id[port_id]
        devports = self._ports_by_device.get(port.deviceId, [])
        if port in devports:
            devports.remove(port)
        device = self._devices_by_id.get(port.deviceId)
        if device and port_id in device.portIds:
            device.portIds.remove(port_id)
            await self._sync_device(device)
        await self._memory.delete_row("ports", port_id)
        self._dirty = True

    def list_ports(self, device_id: str) -> list[Port]:
        return self._ports_by_device.get(device_id, [])

    def get_port(self, port_id: str) -> Port:
        p = self._ports_by_id.get(port_id)
        if p is None:
            raise AppError(ERROR_NOT_FOUND, f"端口 '{port_id}' 不存在", status_code=404)
        return p

    # ------------------------------------------------------------------
    # Link CRUD
    # ------------------------------------------------------------------

    async def create_link(self, req: LinkCreate) -> Link:
        # Validate devices and ports exist
        self.get_device(req.sourceDeviceId)
        self.get_device(req.targetDeviceId)
        src_port = self.get_port(req.sourcePortId)
        tgt_port = self.get_port(req.targetPortId)

        if src_port.status == "connected":
            raise AppError(ERROR_CONFLICT, f"源端口 '{src_port.name}' 已连接", status_code=409)
        if tgt_port.status == "connected":
            raise AppError(ERROR_CONFLICT, f"目标端口 '{tgt_port.name}' 已连接", status_code=409)

        link = Link(id=_uid("link_"), **req.model_dump())
        self._data.links.append(link)
        self._links_by_id[link.id] = link

        # Update port status
        src_port.status = "connected"
        tgt_port.status = "connected"
        await self._sync_port(src_port)
        await self._sync_port(tgt_port)
        await self._sync_link(link)

        self._dirty = True
        await event_bus.emit("topology.link.created", link=link.model_dump())
        return link

    async def update_link(self, link_id: str, **kwargs: Any) -> Link:
        link = self._links_by_id.get(link_id)
        if link is None:
            raise AppError(ERROR_NOT_FOUND, f"链路 '{link_id}' 不存在", status_code=404)
        for k, v in kwargs.items():
            if v is not None and hasattr(link, k):
                setattr(link, k, v)
        await self._sync_link(link)
        self._dirty = True
        return link

    async def delete_link(self, link_id: str) -> None:
        link = self._links_by_id.get(link_id)
        if link is None:
            raise AppError(ERROR_NOT_FOUND, f"链路 '{link_id}' 不存在", status_code=404)
        await self._remove_link(link)
        self._dirty = True
        await event_bus.emit("topology.link.deleted", linkId=link_id)

    async def batch_delete_links(self, link_ids: list[str]) -> int:
        count = 0
        for lid in link_ids:
            if lid in self._links_by_id:
                await self.delete_link(lid)
                count += 1
        return count

    def list_links(self) -> list[Link]:
        return self._data.links

    async def _remove_link(self, link: Link) -> None:
        """Remove a link and free its ports."""
        # Free ports
        src = self._ports_by_id.get(link.sourcePortId)
        tgt = self._ports_by_id.get(link.targetPortId)
        if src and src.status == "connected":
            src.status = "free"
            await self._sync_port(src)
        if tgt and tgt.status == "connected":
            tgt.status = "free"
            await self._sync_port(tgt)
        self._data.links.remove(link)
        del self._links_by_id[link.id]
        await self._memory.delete_row("links", link.id)

    # ------------------------------------------------------------------
    # Alarm CRUD
    # ------------------------------------------------------------------

    async def create_alarm(self, deviceId: str, level: str = "warning", type: str = "",
                           content: str = "", occurTime: str = "") -> Alarm:
        self.get_device(deviceId)  # validate device exists
        alarm = Alarm(
            id=_uid("alarm_"),
            deviceId=deviceId,
            level=level,
            type=type,
            content=content,
            status="active",
            occurTime=occurTime or datetime.now(timezone.utc).isoformat(),
        )
        self._data.alarms.append(alarm)
        self._alarms_by_id[alarm.id] = alarm
        await self._sync_alarm(alarm)
        self._dirty = True
        await event_bus.emit("alarm.created", alarm=alarm.model_dump())
        return alarm

    async def clear_alarm(self, alarm_id: str) -> Alarm:
        alarm = self._alarms_by_id.get(alarm_id)
        if alarm is None:
            raise AppError(ERROR_NOT_FOUND, f"告警 '{alarm_id}' 不存在", status_code=404)
        alarm.status = "cleared"
        alarm.clearTime = datetime.now(timezone.utc).isoformat()
        await self._sync_alarm(alarm)
        self._dirty = True
        await event_bus.emit("alarm.cleared", alarm=alarm.model_dump())
        return alarm

    async def delete_alarm(self, alarm_id: str) -> None:
        alarm = self._alarms_by_id.get(alarm_id)
        if alarm is None:
            raise AppError(ERROR_NOT_FOUND, f"告警 '{alarm_id}' 不存在", status_code=404)
        self._data.alarms.remove(alarm)
        del self._alarms_by_id[alarm_id]
        await self._memory.delete_row("alarms", alarm_id)
        self._dirty = True

    async def batch_create_alarms(self, alarms_data: list[dict]) -> list[Alarm]:
        results = []
        for a in alarms_data:
            alarm = await self.create_alarm(**a)
            results.append(alarm)
        return results

    def list_alarms(self, device_id: str | None = None, level: str | None = None,
                    status: str | None = None) -> list[Alarm]:
        result = self._data.alarms
        if device_id:
            result = [a for a in result if a.deviceId == device_id]
        if level:
            result = [a for a in result if a.level == level]
        if status:
            result = [a for a in result if a.status == status]
        return result

    # ------------------------------------------------------------------
    # Metric CRUD
    # ------------------------------------------------------------------

    async def create_metric(self, deviceId: str, name: str, value: float = 0.0,
                            unit: str = "", collectTime: str = "", collectInterval: int = 300) -> Metric:
        self.get_device(deviceId)
        metric = Metric(
            id=_uid("metric_"),
            deviceId=deviceId,
            name=name,
            value=value,
            unit=unit,
            collectTime=collectTime or datetime.now(timezone.utc).isoformat(),
            collectInterval=collectInterval,
        )
        self._data.metrics.append(metric)
        self._metrics_by_id[metric.id] = metric
        await self._sync_metric(metric)
        self._dirty = True
        return metric

    async def update_metric(self, metric_id: str, **kwargs: Any) -> Metric:
        metric = self._metrics_by_id.get(metric_id)
        if metric is None:
            raise AppError(ERROR_NOT_FOUND, f"指标 '{metric_id}' 不存在", status_code=404)
        for k, v in kwargs.items():
            if v is not None and hasattr(metric, k):
                setattr(metric, k, v)
        await self._sync_metric(metric)
        self._dirty = True
        return metric

    async def delete_metric(self, metric_id: str) -> None:
        metric = self._metrics_by_id.get(metric_id)
        if metric is None:
            raise AppError(ERROR_NOT_FOUND, f"指标 '{metric_id}' 不存在", status_code=404)
        self._data.metrics.remove(metric)
        del self._metrics_by_id[metric_id]
        await self._memory.delete_row("metrics", metric_id)
        self._dirty = True

    def list_metrics(self, device_id: str | None = None) -> list[Metric]:
        if device_id:
            return [m for m in self._data.metrics if m.deviceId == device_id]
        return self._data.metrics

    # ------------------------------------------------------------------
    # Canvas
    # ------------------------------------------------------------------

    def update_canvas(self, canvas: dict) -> CanvasState:
        if "zoom" in canvas:
            self._data.canvas.zoom = canvas["zoom"]
        if "offset" in canvas:
            self._data.canvas.offset = canvas["offset"]
        if "nodePositions" in canvas:
            self._data.canvas.nodePositions.update(canvas["nodePositions"])
        self._dirty = True
        return self._data.canvas

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        # Check duplicate names
        names: dict[str, list[str]] = {}
        for d in self._data.devices:
            names.setdefault(d.name, []).append(d.id)
        for name, ids in names.items():
            if len(ids) > 1:
                issues.append(ValidationIssue(
                    level="error", type="duplicate_name",
                    message=f"设备名称 '{name}' 重复 ({len(ids)} 个)",
                    target=",".join(ids), fixable=True,
                    suggestion=f"自动追加后缀 -2, -3 等",
                ))

        # Check link port references
        for link in self._data.links:
            if link.sourcePortId not in self._ports_by_id:
                issues.append(ValidationIssue(
                    level="error", type="invalid_port_ref",
                    message=f"链路 '{link.id}' 源端口 '{link.sourcePortId}' 不存在",
                    target=link.id, fixable=False,
                ))
            if link.targetPortId not in self._ports_by_id:
                issues.append(ValidationIssue(
                    level="error", type="invalid_port_ref",
                    message=f"链路 '{link.id}' 目标端口 '{link.targetPortId}' 不存在",
                    target=link.id, fixable=False,
                ))

        # Check orphan ports (port deviceId doesn't exist)
        for port in self._data.ports:
            if port.deviceId not in self._devices_by_id:
                issues.append(ValidationIssue(
                    level="warning", type="orphan_port",
                    message=f"端口 '{port.name}' 关联的设备 '{port.deviceId}' 不存在",
                    target=port.id, fixable=True,
                    suggestion="删除孤立端口",
                ))

        # Check devices with empty name
        for d in self._data.devices:
            if not d.name.strip():
                issues.append(ValidationIssue(
                    level="error", type="empty_name",
                    message=f"设备 '{d.id}' 名称为空",
                    target=d.id, fixable=False,
                ))

        return issues

    async def fix_issues(self) -> list[str]:
        """Fix all fixable issues. Returns list of fix descriptions."""
        fixes: list[str] = []

        # Fix duplicate names
        names: dict[str, list[Device]] = {}
        for d in self._data.devices:
            names.setdefault(d.name, []).append(d)
        for name, devs in names.items():
            if len(devs) > 1:
                for i, d in enumerate(devs[1:], 2):
                    new_name = f"{name}-{i}"
                    d.name = new_name
                    d.dn = self._compute_device_dn(d)
                    await self._sync_device(d)
                    fixes.append(f"重命名设备 '{d.id}' 为 '{new_name}'")

        # Fix orphan ports
        orphans = [p for p in self._data.ports if p.deviceId not in self._devices_by_id]
        for port in orphans:
            self._data.ports.remove(port)
            self._ports_by_id.pop(port.id, None)
            await self._memory.delete_row("ports", port.id)
            fixes.append(f"删除孤立端口 '{port.id}'")

        if fixes:
            self._dirty = True
        return fixes

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compute_layout(self, algorithm: str = "grid", options: dict | None = None) -> dict[str, dict[str, float]]:
        opts = options or {}
        devices = self._data.devices
        if not devices:
            return {}

        if algorithm == "grid":
            return self._layout_grid(devices, opts)
        elif algorithm == "circular":
            return self._layout_circular(devices, opts)
        elif algorithm == "hierarchical":
            return self._layout_hierarchical(devices, opts)
        elif algorithm == "force":
            return self._layout_force(devices, opts)
        else:
            return self._layout_grid(devices, opts)

    @staticmethod
    def _layout_grid(devices: list[Device], opts: dict) -> dict[str, dict[str, float]]:
        spacing_x = opts.get("spacingX", 200)
        spacing_y = opts.get("spacingY", 150)
        cols = opts.get("columns", max(1, int(math.sqrt(len(devices)))))
        positions = {}
        for i, d in enumerate(devices):
            row, col = divmod(i, cols)
            positions[d.id] = {"x": col * spacing_x + 100, "y": row * spacing_y + 100}
        return positions

    @staticmethod
    def _layout_circular(devices: list[Device], opts: dict) -> dict[str, dict[str, float]]:
        radius = opts.get("radius", max(200, len(devices) * 30))
        cx, cy = opts.get("centerX", 500), opts.get("centerY", 400)
        positions = {}
        n = len(devices)
        for i, d in enumerate(devices):
            angle = 2 * math.pi * i / n
            positions[d.id] = {"x": cx + radius * math.cos(angle), "y": cy + radius * math.sin(angle)}
        return positions

    def _layout_hierarchical(self, devices: list[Device], opts: dict) -> dict[str, dict[str, float]]:
        spacing_x = opts.get("spacingX", 200)
        spacing_y = opts.get("spacingY", 150)
        # Build adjacency from links
        children: dict[str, set[str]] = {d.id: set() for d in devices}
        linked: set[str] = set()
        for link in self._data.links:
            if link.sourceDeviceId in children and link.targetDeviceId in children:
                children[link.sourceDeviceId].add(link.targetDeviceId)
                linked.add(link.targetDeviceId)
        # Roots = devices not targeted by any link
        roots = [d.id for d in devices if d.id not in linked]
        if not roots:
            roots = [devices[0].id]

        # BFS layering
        layers: list[list[str]] = []
        visited: set[str] = set()
        current = roots
        while current:
            layer = []
            next_layer = []
            for nid in current:
                if nid not in visited:
                    visited.add(nid)
                    layer.append(nid)
                    next_layer.extend(children.get(nid, set()))
            if layer:
                layers.append(layer)
            current = next_layer
        # Add unvisited
        unvisited = [d.id for d in devices if d.id not in visited]
        if unvisited:
            layers.append(unvisited)

        positions = {}
        for ly, layer in enumerate(layers):
            for lx, did in enumerate(layer):
                positions[did] = {"x": lx * spacing_x + 100, "y": ly * spacing_y + 100}
        return positions

    @staticmethod
    def _layout_force(devices: list[Device], opts: dict) -> dict[str, dict[str, float]]:
        # Simple random initial positions (proper force sim is complex; grid is fine for MVP)
        import random
        random.seed(42)
        positions = {}
        for d in devices:
            positions[d.id] = {"x": random.uniform(100, 1000), "y": random.uniform(100, 800)}
        return positions

    # ------------------------------------------------------------------
    # Import / Export
    # ------------------------------------------------------------------

    def export_data(self) -> dict:
        return self.serialize()

    def import_data(self, data: dict) -> None:
        """Import topology data, re-assign IDs to avoid conflicts."""
        self.load_data(data)

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        return {
            "devices": len(self._data.devices),
            "ports": len(self._data.ports),
            "links": len(self._data.links),
            "alarms": len(self._data.alarms),
            "metrics": len(self._data.metrics),
        }

    # ------------------------------------------------------------------
    # Memory sync helpers
    # ------------------------------------------------------------------

    async def _sync_device(self, device: Device) -> None:
        d = device.model_dump()
        d["portCount"] = len(device.portIds)
        d["customFields"] = d.get("customFields", {})
        await self._memory.upsert_row("devices", d)

    async def _sync_port(self, port: Port) -> None:
        await self._memory.upsert_row("ports", port.model_dump())

    async def _sync_link(self, link: Link) -> None:
        await self._memory.upsert_row("links", link.model_dump())

    async def _sync_alarm(self, alarm: Alarm) -> None:
        await self._memory.upsert_row("alarms", alarm.model_dump())

    async def _sync_metric(self, metric: Metric) -> None:
        await self._memory.upsert_row("metrics", metric.model_dump())
