#!/usr/bin/env python3
"""Minimal web demo for the COLREG expert system.

Run from the project root:
    uv run python scripts/demo_web.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.engine import COLREGInferenceEngine
from src.models import Environment, Vessel, VesselType, Visibility


HOST = "127.0.0.1"
START_PORT = 8080


@dataclass(frozen=True)
class DemoPreset:
    id: str
    title: str
    subtitle: str
    rule_focus: str
    own: Vessel
    targets: tuple[Vessel, ...]
    env: Environment
    wind_direction: Optional[float] = None


PRESETS: tuple[DemoPreset, ...] = (
    DemoPreset(
        id="head-on",
        title="Встречные курсы",
        subtitle=(
            "Два механических судна идут нос к носу. Должно сработать правило 14: "
            "оба судна меняют курс вправо; итоговая рекомендация - поворот вправо."
        ),
        rule_focus="Правило 14",
        own=Vessel("Наше судно", 0, 0, 0, 10, VesselType.POWER_DRIVEN),
        targets=(Vessel("Цель A", 0, 1.5, 180, 10, VesselType.POWER_DRIVEN),),
        env=Environment(visibility=Visibility.GOOD),
    ),
    DemoPreset(
        id="crossing-starboard",
        title="Цель справа",
        subtitle=(
            "Пересечение курсов: цель находится по правому борту. Должно сработать "
            "правило 15: наше судно уступает дорогу; итоговая рекомендация - поворот вправо."
        ),
        rule_focus="Правило 15",
        own=Vessel("Наше судно", 0, 0, 0, 10, VesselType.POWER_DRIVEN),
        targets=(Vessel("Цель A", 1.0, 1.0, 270, 10, VesselType.POWER_DRIVEN),),
        env=Environment(visibility=Visibility.GOOD),
    ),
    DemoPreset(
        id="overtaking",
        title="Обгон",
        subtitle=(
            "Наше судно догоняет более медленную цель. Должно сработать правило 13: "
            "обгоняющее судно держится в стороне; итоговая рекомендация - поворот вправо."
        ),
        rule_focus="Правило 13",
        own=Vessel("Наше судно", 0, 0, 0, 15, VesselType.POWER_DRIVEN),
        targets=(Vessel("Цель A", 0, 1, 0, 8, VesselType.POWER_DRIVEN),),
        env=Environment(visibility=Visibility.GOOD),
    ),
    DemoPreset(
        id="sailing-priority",
        title="Парусное судно",
        subtitle=(
            "Механическое судно встречает парусное. Должно сработать правило 18: "
            "механическое судно уступает парусному; итоговая рекомендация - поворот вправо."
        ),
        rule_focus="Правило 18",
        own=Vessel("Наше судно", 0, 0, 0, 10, VesselType.POWER_DRIVEN),
        targets=(Vessel("Парусник", -1.0, 1.0, 90, 10, VesselType.SAILING),),
        env=Environment(visibility=Visibility.GOOD),
    ),
    DemoPreset(
        id="restricted-visibility",
        title="Ограниченная видимость",
        subtitle=(
            "Та же геометрия при ограниченной видимости. Должно сработать правило 19: "
            "система запрещает опасные повороты; итоговая рекомендация - поворот вправо."
        ),
        rule_focus="Правило 19",
        own=Vessel("Наше судно", 0, 0, 0, 10, VesselType.POWER_DRIVEN),
        targets=(Vessel("Цель A", 1.0, 1.0, 270, 10, VesselType.POWER_DRIVEN),),
        env=Environment(visibility=Visibility.RESTRICTED),
    ),
    DemoPreset(
        id="multi-target",
        title="Две цели",
        subtitle=(
            "Две цели создают пересекающиеся опасные сектора. Должны сработать правила "
            "пересечения курсов для каждой цели; итоговая рекомендация - общий безопасный курс."
        ),
        rule_focus="Многоцелевой вывод",
        own=Vessel("Наше судно", 0, 0, 0, 12, VesselType.POWER_DRIVEN),
        targets=(
            Vessel("Цель A", 1.0, 1.0, 270, 10, VesselType.POWER_DRIVEN),
            Vessel("Цель B", -1.0, 1.0, 90, 10, VesselType.POWER_DRIVEN),
        ),
        env=Environment(visibility=Visibility.GOOD),
    ),
    DemoPreset(
        id="turning-limit",
        title="Маневр не успевает",
        subtitle=(
            "Близкое встречное сближение и большой радиус циркуляции. Должно сработать "
            "правило 14, но проверка маневренности показывает: поворот не успевает завершиться."
        ),
        rule_focus="Ограничение маневренности",
        own=Vessel(
            "Наше судно",
            0,
            0,
            0,
            20,
            VesselType.POWER_DRIVEN,
            min_turning_radius=0.8,
        ),
        targets=(Vessel("Цель A", 0, 0.3, 180, 10, VesselType.POWER_DRIVEN),),
        env=Environment(visibility=Visibility.GOOD),
    ),
)


ACTION_LABELS = {
    "KEEP_COURSE_SPEED": "Сохранять курс и скорость",
    "ALTER_COURSE_STARBOARD": "Поворот вправо",
    "ALTER_COURSE_PORT": "Поворот влево",
    "REDUCE_SPEED_OR_STOP": "Снизить ход / остановиться",
    "N_A": "Маневр не требуется",
}

ROLE_LABELS = {
    "STAND_ON": "Имеем преимущество",
    "GIVE_WAY": "Уступаем дорогу",
    "BOTH": "Оба маневрируют",
    "N_A": "Не применимо",
}

ENCOUNTER_LABELS = {
    "SAFE": "безопасно",
    "UNKNOWN": "не определено",
    "RESTRICTED": "ограниченная видимость",
    "own_overtaking": "мы обгоняем",
    "target_overtaking": "нас обгоняют",
    "head_on": "встречные курсы",
    "crossing_starboard": "цель справа",
    "crossing_port": "цель слева",
    "priority": "приоритет типа судна",
    "sailing_diff_tack": "разные галсы",
    "sailing_same_tack": "одинаковые галсы",
    "restricted_ahead": "цель впереди",
    "restricted_ahead_overtaking": "обгон в тумане",
    "restricted_abaft_starboard": "позади справа",
    "restricted_abaft_port": "позади слева",
}

RULE_LABELS = {
    "rule_12": "Правило 12: парусные суда",
    "rule_13": "Правило 13: обгон",
    "rule_14": "Правило 14: встречные курсы",
    "rule_15": "Правило 15: пересечение курсов",
    "rule_17": "Правило 17: действие судна с преимуществом",
    "rule_18": "Правило 18: приоритет типов судов",
    "rule_19": "Правило 19: ограниченная видимость",
}

TYPE_LABELS = {
    "POWER_DRIVEN": "механическое",
    "SAILING": "парусное",
    "FISHING": "рыболовное",
    "CBD": "стеснено осадкой",
    "RAM": "ограничено в маневре",
    "NUC": "не управляется",
}


def _vessel_to_dict(vessel: Vessel) -> dict:
    return {
        "name": vessel.name,
        "x": vessel.x,
        "y": vessel.y,
        "course": vessel.course,
        "speed": vessel.speed,
        "type": vessel.vessel_type.value,
        "type_label": TYPE_LABELS[vessel.vessel_type.value],
        "min_turning_radius": vessel.min_turning_radius,
    }


def _target_decision_to_dict(decision) -> dict:
    return {
        "target_name": decision.target_name,
        "collision_risk": decision.collision_risk,
        "encounter_type": decision.encounter_type,
        "encounter_type_label": ENCOUNTER_LABELS.get(
            decision.encounter_type,
            decision.encounter_type.replace("_", " "),
        ),
        "own_role": decision.own_role.value,
        "own_role_label": ROLE_LABELS[decision.own_role.value],
        "recommended_action": decision.recommended_action.value,
        "recommended_action_label": ACTION_LABELS[decision.recommended_action.value],
        "cpa": round(decision.cpa, 3),
        "tcpa_minutes": None if decision.tcpa == float("inf") else round(decision.tcpa * 60, 1),
        "fired_rules": decision.fired_rules,
    }


def _preset_result(preset: DemoPreset) -> dict:
    engine = COLREGInferenceEngine()
    decision = engine.evaluate(
        preset.own,
        list(preset.targets),
        preset.env,
        wind_direction=preset.wind_direction,
    )
    primary_rules = _primary_rules_for_preset(preset, sorted(set(decision.fired_rules)))
    return {
        "id": preset.id,
        "title": preset.title,
        "subtitle": preset.subtitle,
        "rule_focus": preset.rule_focus,
        "environment": {
            "visibility": preset.env.visibility.value,
            "visibility_label": "хорошая" if preset.env.visibility == Visibility.GOOD else "ограниченная",
        },
        "own": _vessel_to_dict(preset.own),
        "targets": [_vessel_to_dict(t) for t in preset.targets],
        "decision": {
            "collision_risk": decision.collision_risk,
            "own_role": decision.own_role.value,
            "own_role_label": ROLE_LABELS[decision.own_role.value],
            "recommended_action": decision.recommended_action.value,
            "recommended_action_label": ACTION_LABELS[decision.recommended_action.value],
            "recommended_heading": decision.recommended_heading,
            "maneuver_possible": decision.maneuver_possible,
            "forbidden_sectors": [
                {"start": round(start), "end": round(end)}
                for start, end in decision.forbidden_sectors
            ],
            "target_decisions": [
                _target_decision_to_dict(td)
                for td in decision.target_decisions.values()
            ],
            "explanation": decision.explanation,
            "fired_rules": sorted(set(decision.fired_rules)),
            "primary_rules": primary_rules,
            "trace_count": decision.trace.fired_count,
        },
    }


def _primary_rules_for_preset(preset: DemoPreset, fired_rules: list[str]) -> list[str]:
    if preset.rule_focus == "Многоцелевой вывод":
        prefixes = ("rule_14", "rule_15", "rule_13", "rule_18", "rule_19")
    elif preset.rule_focus == "Ограничение маневренности":
        prefixes = ("rule_14", "rule_17")
    else:
        prefixes = (preset.rule_focus.lower().replace("правило ", "rule_"),)

    selected = [
        rule for rule in fired_rules
        if any(rule.startswith(prefix) for prefix in prefixes)
    ]
    labels: list[str] = []
    for rule in selected:
        for prefix, label in RULE_LABELS.items():
            if rule.startswith(prefix) and label not in labels:
                labels.append(label)
                break
    return labels[:4]


def presets_payload() -> dict:
    return {"presets": [_preset_result(preset) for preset in PRESETS]}


HTML = r"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>COLREG Expert Demo</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f4;
      --panel: #ffffff;
      --ink: #202324;
      --muted: #697071;
      --line: #d9ddd8;
      --accent: #0f766e;
      --accent-2: #b42318;
      --amber: #b7791f;
      --blue: #2563eb;
      --shadow: 0 14px 36px rgba(32, 35, 36, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }

    button { font: inherit; }

    .app {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 310px minmax(0, 1fr);
    }

    .sidebar {
      border-right: 1px solid var(--line);
      padding: 24px 18px;
      background: #fbfbf8;
    }

    .preset-list {
      display: grid;
      gap: 8px;
    }

    .preset {
      width: 100%;
      min-height: 52px;
      padding: 12px;
      border: 1px solid transparent;
      border-radius: 8px;
      background: transparent;
      color: var(--ink);
      text-align: left;
      cursor: pointer;
      display: flex;
      align-items: center;
    }

    .preset:hover { background: #f0f2ee; }
    .preset.active {
      background: var(--panel);
      border-color: #bfd7d2;
      box-shadow: 0 8px 22px rgba(15, 118, 110, 0.08);
    }

    .preset strong {
      font-size: 14px;
      line-height: 1.2;
      font-weight: 700;
    }

    .main {
      padding: 28px;
      display: grid;
      grid-template-rows: auto minmax(0, 1fr);
      gap: 20px;
    }

    .scenario-title {
      display: grid;
      gap: 8px;
      max-width: 760px;
    }

    .scenario-title h2 {
      margin: 0;
      font-size: clamp(28px, 4vw, 46px);
      line-height: 1.02;
      font-weight: 760;
    }

    .scenario-title p {
      margin: 0;
      color: var(--muted);
      font-size: 16px;
      line-height: 1.5;
    }

    .grid {
      min-height: 0;
      display: grid;
      grid-template-columns: minmax(360px, 0.95fr) minmax(420px, 1.05fr);
      gap: 18px;
      align-items: stretch;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      min-width: 0;
    }

    .radar-panel {
      padding: 16px;
      display: grid;
      grid-template-rows: auto minmax(260px, 1fr);
      gap: 12px;
    }

    .panel-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }

    .panel-head h3 {
      margin: 0;
      font-size: 15px;
      font-weight: 730;
    }

    .meta {
      color: var(--muted);
      font-size: 12px;
    }

    .radar-wrap {
      min-height: 260px;
      position: relative;
    }

    canvas {
      width: 100%;
      height: 100%;
      min-height: 420px;
      display: block;
      border-radius: 8px;
      background: #f4f7f5;
      border: 1px solid #e1e5df;
    }

    .details {
      padding: 16px;
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr);
      gap: 14px;
      min-height: 0;
    }

    .decision {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      min-height: 88px;
      display: grid;
      align-content: center;
      gap: 7px;
      background: #fbfbf8;
    }

    .metric span {
      color: var(--muted);
      font-size: 12px;
    }

    .metric strong {
      font-size: 18px;
      line-height: 1.2;
      overflow-wrap: anywhere;
    }

    .metric.risk strong { color: var(--accent-2); }
    .metric.ok strong { color: var(--accent); }
    .metric.warn strong { color: var(--amber); }

    .targets {
      display: grid;
      gap: 8px;
    }

    .target-row {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px 12px;
      display: grid;
      gap: 8px;
    }

    .target-row strong {
      font-size: 14px;
    }

    .target-facts {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
    }

    .fact {
      display: grid;
      gap: 3px;
      min-width: 0;
    }

    .fact span {
      color: var(--muted);
      font-size: 11px;
      line-height: 1.2;
    }

    .fact strong {
      font-size: 13px;
      line-height: 1.25;
      overflow-wrap: anywhere;
    }

    .applied-rule {
      margin-top: 12px;
      border-top: 1px solid var(--line);
      padding-top: 10px;
      display: grid;
      gap: 3px;
    }

    .applied-rule span {
      color: var(--muted);
      font-size: 12px;
    }

    .applied-rule strong {
      color: #0f5f59;
      font-size: 14px;
      line-height: 1.35;
    }

    .explain {
      min-height: 0;
      overflow: auto;
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }

    .explain h3 {
      margin: 0 0 10px;
      font-size: 15px;
    }

    .explain ul {
      margin: 0;
      padding: 0;
      list-style: none;
      display: grid;
      gap: 7px;
    }

    .explain li {
      color: #333838;
      font-size: 13px;
      line-height: 1.45;
      padding-left: 14px;
      position: relative;
    }

    .explain li::before {
      content: "";
      position: absolute;
      left: 0;
      top: 0.65em;
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: var(--accent);
    }

    @media (max-width: 980px) {
      .app { grid-template-columns: 1fr; }
      .sidebar {
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
      .preset-list {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
      .grid { grid-template-columns: 1fr; }
      .main { padding: 20px; }
    }

    @media (max-width: 640px) {
      .preset-list { grid-template-columns: 1fr; }
      .decision { grid-template-columns: 1fr; }
      .target-facts { grid-template-columns: 1fr 1fr; }
      canvas { min-height: 320px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div id="presetList" class="preset-list"></div>
    </aside>

    <main class="main">
      <section class="topline">
        <div class="scenario-title">
          <h2 id="title">Загрузка...</h2>
          <p id="subtitle"></p>
        </div>
      </section>

      <section class="grid">
        <div class="panel radar-panel">
          <div class="panel-head">
            <h3>Навигационная обстановка</h3>
            <span id="env" class="meta"></span>
          </div>
          <div class="radar-wrap">
            <canvas id="radar"></canvas>
          </div>
        </div>

        <div class="panel details">
          <div class="decision">
            <div id="riskMetric" class="metric">
              <span>Риск</span>
              <strong id="risk"></strong>
            </div>
            <div class="metric">
              <span>Действие</span>
              <strong id="action"></strong>
            </div>
            <div id="turnMetric" class="metric">
              <span>Курс / маневр</span>
              <strong id="heading"></strong>
            </div>
          </div>

          <div id="targets" class="targets"></div>

          <div class="explain">
            <h3>Объяснение вывода</h3>
            <ul id="explain"></ul>
            <div id="rules" class="applied-rule"></div>
          </div>
        </div>
      </section>
    </main>
  </div>

  <script>
    const state = { presets: [], active: 0 };

    const $ = (id) => document.getElementById(id);

    function formatHeading(value) {
      return value === null || value === undefined ? "нет" : `${Math.round(value)}°`;
    }

    function cleanLine(line) {
      return line
        .replace(/^-+\s*$/, "")
        .replace(/^\s*-\s*/, "")
        .replace(/:;$/, ":")
        .trim();
    }

    function selectPreset(index) {
      state.active = index;
      renderPresetList();
      renderScenario(state.presets[index]);
    }

    function renderPresetList() {
      $("presetList").innerHTML = "";
      state.presets.forEach((preset, index) => {
        const button = document.createElement("button");
        button.className = `preset ${index === state.active ? "active" : ""}`;
        button.type = "button";
        button.innerHTML = `<strong>${preset.title}</strong>`;
        button.addEventListener("click", () => selectPreset(index));
        $("presetList").appendChild(button);
      });
    }

    function renderScenario(preset) {
      const decision = preset.decision;
      $("title").textContent = preset.title;
      $("subtitle").textContent = preset.subtitle;
      $("env").textContent = `Видимость: ${preset.environment.visibility_label}`;

      $("risk").textContent = decision.collision_risk ? "есть" : "нет";
      $("riskMetric").className = `metric ${decision.collision_risk ? "risk" : "ok"}`;
      $("action").textContent = decision.recommended_action_label;
      $("heading").textContent = decision.maneuver_possible
        ? formatHeading(decision.recommended_heading)
        : "не успевает";
      $("turnMetric").className = `metric ${decision.maneuver_possible ? "" : "warn"}`;

      $("targets").innerHTML = "";
      decision.target_decisions.forEach((target) => {
        const row = document.createElement("div");
        row.className = "target-row";
        const tcpa = target.tcpa_minutes === null ? "не сближается" : `${target.tcpa_minutes} мин`;
        row.innerHTML = `
          <strong>${target.target_name}</strong>
          <div class="target-facts">
            <div class="fact"><span>Тип ситуации</span><strong>${target.encounter_type_label}</strong></div>
            <div class="fact"><span>Роль нашего судна</span><strong>${target.own_role_label}</strong></div>
            <div class="fact"><span>CPA</span><strong>${target.cpa} миль</strong></div>
            <div class="fact"><span>TCPA</span><strong>${tcpa}</strong></div>
          </div>
        `;
        $("targets").appendChild(row);
      });

      const lines = decision.explanation.map(cleanLine).filter(Boolean).slice(0, 11);
      $("explain").innerHTML = lines.map((line) => `<li>${line}</li>`).join("");
      $("rules").innerHTML = decision.primary_rules.length
        ? `<span>Примененное правило</span><strong>${decision.primary_rules.join(", ")}</strong>`
        : "";

      drawRadar(preset);
    }

    function resizeCanvas(canvas) {
      const rect = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(rect.width * ratio));
      canvas.height = Math.max(1, Math.floor(rect.height * ratio));
      const ctx = canvas.getContext("2d");
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      return { ctx, width: rect.width, height: rect.height };
    }

    function drawArrow(ctx, x, y, course, length, color, label) {
      const rad = course * Math.PI / 180;
      const dx = Math.sin(rad) * length;
      const dy = -Math.cos(rad) * length;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + dx, y + dy);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill();

      const angle = Math.atan2(dy, dx);
      ctx.beginPath();
      ctx.moveTo(x + dx, y + dy);
      ctx.lineTo(x + dx - Math.cos(angle - 0.55) * 10, y + dy - Math.sin(angle - 0.55) * 10);
      ctx.lineTo(x + dx - Math.cos(angle + 0.55) * 10, y + dy - Math.sin(angle + 0.55) * 10);
      ctx.closePath();
      ctx.fill();

      ctx.font = "12px system-ui, sans-serif";
      ctx.fillText(label, x + 9, y - 9);
    }

    function drawForbiddenSectors(ctx, cx, cy, radius, sectors) {
      ctx.fillStyle = "rgba(180, 35, 24, 0.14)";
      sectors.forEach(({ start, end }) => {
        const draw = (a, b) => {
          ctx.beginPath();
          ctx.moveTo(cx, cy);
          ctx.arc(cx, cy, radius, (a - 90) * Math.PI / 180, (b - 90) * Math.PI / 180);
          ctx.closePath();
          ctx.fill();
        };
        if (start <= end) draw(start, end);
        else {
          draw(start, 359);
          draw(0, end);
        }
      });
    }

    function drawRadar(preset) {
      const canvas = $("radar");
      const { ctx, width, height } = resizeCanvas(canvas);
      const cx = width / 2;
      const cy = height / 2;
      const all = [preset.own, ...preset.targets];
      const extent = Math.max(2.4, ...all.map((v) => Math.max(Math.abs(v.x), Math.abs(v.y)))) * 1.25;
      const radius = Math.min(width, height) * 0.42;
      const scale = radius / extent;

      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = "#f4f7f5";
      ctx.fillRect(0, 0, width, height);

      ctx.strokeStyle = "#d9ddd8";
      ctx.lineWidth = 1;
      [0.33, 0.66, 1].forEach((r) => {
        ctx.beginPath();
        ctx.arc(cx, cy, radius * r, 0, Math.PI * 2);
        ctx.stroke();
      });
      ctx.beginPath();
      ctx.moveTo(cx - radius, cy);
      ctx.lineTo(cx + radius, cy);
      ctx.moveTo(cx, cy - radius);
      ctx.lineTo(cx, cy + radius);
      ctx.stroke();

      drawForbiddenSectors(ctx, cx, cy, radius, preset.decision.forbidden_sectors);

      const toScreen = (v) => [cx + v.x * scale, cy - v.y * scale];
      preset.targets.forEach((target) => {
        const [x, y] = toScreen(target);
        drawArrow(ctx, x, y, target.course, 38, "#b42318", target.name);
      });
      const [ownX, ownY] = toScreen(preset.own);
      drawArrow(ctx, ownX, ownY, preset.own.course, 46, "#0f766e", preset.own.name);

      const heading = preset.decision.recommended_heading;
      if (heading !== null && heading !== undefined) {
        const rad = heading * Math.PI / 180;
        ctx.strokeStyle = "#2563eb";
        ctx.setLineDash([6, 5]);
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(ownX, ownY);
        ctx.lineTo(ownX + Math.sin(rad) * radius * 0.72, ownY - Math.cos(rad) * radius * 0.72);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      ctx.fillStyle = "#697071";
      ctx.font = "12px system-ui, sans-serif";
      ctx.fillText("красный сектор: опасные курсы", 14, height - 16);
    }

    async function init() {
      const response = await fetch("/api/presets");
      const payload = await response.json();
      state.presets = payload.presets;
      renderPresetList();
      renderScenario(state.presets[0]);
      window.addEventListener("resize", () => renderScenario(state.presets[state.active]));
    }

    init().catch((error) => {
      $("title").textContent = "Ошибка загрузки";
      $("subtitle").textContent = error.message;
    });
  </script>
</body>
</html>
"""


class DemoHandler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, b"", "text/html; charset=utf-8")
        elif path == "/api/presets":
            self._send(200, b"", "application/json; charset=utf-8")
        else:
            self._send(404, b"", "text/plain; charset=utf-8")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/presets":
            payload = json.dumps(presets_payload(), ensure_ascii=False).encode("utf-8")
            self._send(200, payload, "application/json; charset=utf-8")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = None
    port = START_PORT
    for candidate in range(START_PORT, START_PORT + 20):
        try:
            server = ThreadingHTTPServer((HOST, candidate), DemoHandler)
            port = candidate
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError("No free demo port found")

    print(f"Demo interface: http://{HOST}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
