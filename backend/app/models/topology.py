"""Pydantic models for topology data."""

from typing import Any

from pydantic import BaseModel, Field


class Device(BaseModel):
    id: str
    name: str
    type: str
    dn: str = ""
    dnTemplate: str = "NE={id}"
    ip: str = ""
    vendor: str = ""
    model: str = ""
    status: str = "online"
    portIds: list[str] = Field(default_factory=list)
    customFields: dict[str, Any] = Field(default_factory=dict)


class Port(BaseModel):
    id: str
    deviceId: str
    name: str
    dn: str = ""
    dnTemplate: str = "{deviceDn},PORT={index}"
    type: str = "GE"
    speed: str = "1Gbps"
    status: str = "free"


class Link(BaseModel):
    id: str
    sourceDeviceId: str
    sourcePortId: str
    targetDeviceId: str
    targetPortId: str
    type: str = "physical"
    bandwidth: str = "1Gbps"
    status: str = "up"
    description: str = ""


class Alarm(BaseModel):
    id: str
    deviceId: str
    level: str = "warning"
    type: str = ""
    content: str = ""
    status: str = "active"
    occurTime: str = ""
    clearTime: str | None = None


class Metric(BaseModel):
    id: str
    deviceId: str
    name: str
    value: float = 0.0
    unit: str = ""
    collectTime: str = ""
    collectInterval: int = 300


class CanvasState(BaseModel):
    zoom: float = 1.0
    offset: dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})
    nodePositions: dict[str, dict[str, float]] = Field(default_factory=dict)


class TopologyData(BaseModel):
    """Full topology data as stored in the data JSON field."""
    devices: list[Device] = Field(default_factory=list)
    ports: list[Port] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    alarms: list[Alarm] = Field(default_factory=list)
    metrics: list[Metric] = Field(default_factory=list)
    canvas: CanvasState = Field(default_factory=CanvasState)


# --- API request/response schemas ---

class PortGenerateConfig(BaseModel):
    count: int = 1
    prefix: str = "GE1/0/"
    startIndex: int = 1
    type: str = "GE"
    speed: str = "1Gbps"
    dnTemplate: str = "{deviceDn},PORT={index}"


class DeviceCreate(BaseModel):
    name: str
    type: str
    dnTemplate: str = "NE={id}"
    ip: str = ""
    vendor: str = ""
    model: str = ""
    status: str = "online"
    customFields: dict[str, Any] = Field(default_factory=dict)
    portConfig: PortGenerateConfig | None = None
    position: dict[str, float] | None = None


class DeviceUpdate(BaseModel):
    name: str | None = None
    type: str | None = None
    dnTemplate: str | None = None
    ip: str | None = None
    vendor: str | None = None
    model: str | None = None
    status: str | None = None
    customFields: dict[str, Any] | None = None


class LinkCreate(BaseModel):
    sourceDeviceId: str
    sourcePortId: str
    targetDeviceId: str
    targetPortId: str
    type: str = "physical"
    bandwidth: str = "1Gbps"
    status: str = "up"
    description: str = ""


class AlarmCreate(BaseModel):
    deviceId: str
    level: str = "warning"
    type: str = ""
    content: str = ""
    occurTime: str = ""


class MetricCreate(BaseModel):
    deviceId: str
    name: str
    value: float = 0.0
    unit: str = ""
    collectTime: str = ""
    collectInterval: int = 300


class TopologyCreate(BaseModel):
    name: str
    description: str = ""


class TopologyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class LayoutRequest(BaseModel):
    algorithm: str = "grid"
    options: dict[str, Any] = Field(default_factory=dict)


class ValidationIssue(BaseModel):
    level: str  # error / warning
    type: str
    message: str
    target: str = ""
    fixable: bool = False
    suggestion: str = ""
