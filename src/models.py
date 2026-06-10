from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class VesselType(Enum):
    POWER_DRIVEN = "POWER_DRIVEN"  # судно с механическим двигателем
    SAILING = "SAILING"  # парусное судно
    FISHING = "FISHING"  # судно, занятое ловом рыбы
    CBD = "CBD"  # судно, стесненное своей осадкой
    RAM = "RAM"  # судно, ограниченное в возможности маневрировать
    NUC = "NUC"  # судно, лишенное возможности управляться

    def description_ru(self) -> str:
        descriptions = {
            VesselType.POWER_DRIVEN: "судно с механическим двигателем",
            VesselType.SAILING: "парусное судно",
            VesselType.FISHING: "судно, занятое ловом рыбы",
            VesselType.CBD: "судно, стесненное своей осадкой",
            VesselType.RAM: "судно, ограниченное в возможности маневрировать",
            VesselType.NUC: "судно, лишенное возможности управляться",
        }
        return descriptions[self]


class Visibility(Enum):
    GOOD = "GOOD"  # на виду друг у друга при хорошей видимости
    RESTRICTED = "RESTRICTED"  # ограниченная видимость


class Action(Enum):
    KEEP_COURSE_SPEED = "KEEP_COURSE_SPEED"
    ALTER_COURSE_STARBOARD = "ALTER_COURSE_STARBOARD"
    ALTER_COURSE_PORT = "ALTER_COURSE_PORT"
    REDUCE_SPEED_OR_STOP = "REDUCE_SPEED_OR_STOP"
    N_A = "N_A"

    def description_ru(self) -> str:
        descriptions = {
            Action.KEEP_COURSE_SPEED: "сохранять курс и скорость",
            Action.ALTER_COURSE_STARBOARD: "изменить курс вправо (на правый борт)",
            Action.ALTER_COURSE_PORT: "изменить курс влево (на левый борт)",
            Action.REDUCE_SPEED_OR_STOP: "уменьшить ход или остановиться (застопорить ход / дать задний ход)",
            Action.N_A: "особых маневров не требуется",
        }
        return descriptions[self]


class VesselRole(Enum):
    STAND_ON = "STAND_ON"  # судно, которому уступают дорогу
    GIVE_WAY = "GIVE_WAY"  # судно, обязанное уступить дорогу
    BOTH_GIVE_WAY = "BOTH"  # оба судна обязаны предпринять маневр (например, лоб-в-лоб)
    N_A = "N_A"

    def description_ru(self) -> str:
        descriptions = {
            VesselRole.STAND_ON: "судно, которому уступают дорогу",
            VesselRole.GIVE_WAY: "судно, уступающее дорогу",
            VesselRole.BOTH_GIVE_WAY: "оба судна обязаны уступить дорогу и изменить курс",
            VesselRole.N_A: "не применимо",
        }
        return descriptions[self]


@dataclass
class Vessel:
    name: str
    x: float  # Координата X (в морских милях)
    y: float  # Координата Y (в морских милях)
    course: float  # Курс судна (в градусах от 0 до 360, 0 = Север, 90 = Восток)
    speed: float  # Скорость судна (в узлах)
    vessel_type: VesselType = VesselType.POWER_DRIVEN
    min_turning_radius: float = (
        0.25  # Минимальный радиус циркуляции (в милях), около 460 метров
    )


@dataclass
class Environment:
    visibility: Visibility = Visibility.GOOD
    in_narrow_channel: bool = False
    in_tss: bool = False  # система разделения движения


@dataclass
class TargetDecision:
    target_name: str
    collision_risk: bool
    encounter_type: str
    own_role: VesselRole
    recommended_action: Action
    cpa: float
    tcpa: float
    explanation: List[str]
    fired_rules: List[str] = field(default_factory=list)


@dataclass
class ProofStep:
    """Один шаг логического вывода: какое правило сработало с какой подстановкой."""

    rule_id: str
    citation: str
    description: str
    premises_resolved: tuple
    conclusions_resolved: tuple
    substitution: tuple

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "citation": self.citation,
            "description": self.description,
            "premises": [
                {"predicate": name, "args": list(args)}
                for name, args in self.premises_resolved
            ],
            "conclusions": [
                {"predicate": name, "args": list(args)}
                for name, args in self.conclusions_resolved
            ],
            "substitution": dict(self.substitution),
        }


@dataclass
class InferenceTrace:
    """Полная трассировка вывода экспертной системы."""

    steps: List[ProofStep] = field(default_factory=list)
    iterations: int = 0
    fired_count: int = 0

    def to_dict(self) -> dict:
        return {
            "iterations": self.iterations,
            "fired_count": self.fired_count,
            "steps": [s.to_dict() for s in self.steps],
        }

    def fired_rule_ids(self) -> List[str]:
        return [s.rule_id for s in self.steps]


@dataclass
class Decision:
    collision_risk: bool
    own_role: VesselRole
    recommended_action: Action
    recommended_heading: Optional[float]
    forbidden_sectors: List[Tuple[float, float]] = field(
        default_factory=list
    )  # Списки углов (start, end)
    target_decisions: Dict[str, TargetDecision] = field(default_factory=dict)
    maneuver_possible: bool = True
    explanation: List[str] = field(default_factory=list)
    trace: InferenceTrace = field(default_factory=InferenceTrace)
    fired_rules: List[str] = field(default_factory=list)
