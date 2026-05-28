from typing import List, Optional
from pydantic import BaseModel, Field


class TaskIn(BaseModel):
    task_id: str = ""
    title: str
    description: str = ""
    priority: str = "medium"
    category: Optional[str] = None
    required_skills: List[str] = Field(default_factory=list)
    sla_minutes: int = 120


class AssignmentRequest(BaseModel):
    tasks: List[TaskIn]
    now_hhmm: Optional[str] = None


class ResourceIn(BaseModel):
    resource_id: str = ""
    name: str
    skills: List[str] = Field(default_factory=list)
    experience_level: int = Field(default=3, ge=1, le=5)
    status: str = "idle"
    current_tasks: int = Field(default=0, ge=0)
    max_tasks: int = Field(default=3, ge=1)
    shift_start: str = "09:00"
    shift_end: str = "18:00"
    success_rate: float = Field(default=0.85, ge=0, le=1)
    avg_resolution_minutes: float = Field(default=60, ge=1)
    handled_categories: List[str] = Field(default_factory=list)
