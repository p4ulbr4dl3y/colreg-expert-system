import json
import logging
import sys
from typing import Any, Dict, List

import paho.mqtt.client as mqtt

# добавляем корневой каталог в пути импорта для загрузки src
sys.path.append(".")

from src.engine import COLREGInferenceEngine
from src.models import Action, Environment, Vessel, VesselRole, VesselType, Visibility

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ColregExpertNode")

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_COMMAND = "colreg/expert/command"
MQTT_TOPIC_RESULT = "colreg/expert/result"


class ExpertNode:
    def __init__(self):
        logger.info("Инициализация экспертного узла...")
        self.engine = COLREGInferenceEngine()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, "colreg_expert_node"
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info(
                f"Успешное подключение к MQTT-брокеру на {MQTT_BROKER}:{MQTT_PORT}"
            )
            client.subscribe(MQTT_TOPIC_COMMAND)
            logger.info(f"Подписка на топик оформлена: {MQTT_TOPIC_COMMAND}")
        else:
            logger.error(
                f"Не удалось подключиться к MQTT-брокеру. Код ошибки: {reason_code}"
            )

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            logger.info(f"Получена команда: {payload}")
            action = payload.get("action")
            if action == "evaluate":
                self._handle_evaluate_command(payload)
            else:
                logger.warning(f"Неизвестное действие: {action}")
        except json.JSONDecodeError:
            logger.error(f"Не удалось распарсить JSON полезной нагрузки: {msg.payload}")
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {e}")

    def _parse_vessel(self, data: Dict[str, Any]) -> Vessel:
        type_str = data.get("vessel_type", "POWER_DRIVEN")
        try:
            v_type = VesselType[type_str]
        except KeyError:
            v_type = VesselType.POWER_DRIVEN

        return Vessel(
            name=data.get("name", "Unknown"),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            course=float(data.get("course", 0.0)),
            speed=float(data.get("speed", 0.0)),
            vessel_type=v_type,
            min_turning_radius=float(data.get("min_turning_radius", 0.25)),
        )

    def _handle_evaluate_command(self, payload: Dict[str, Any]) -> None:
        request_id = payload.get("request_id", "unknown")

        # парсим собственное судно
        own_data = payload.get("own_ship")
        if not own_data:
            self._publish_error(request_id, "отсутствует own_ship в полезной нагрузке.")
            return

        try:
            own = self._parse_vessel(own_data)

            # парсим список целей
            targets: List[Vessel] = []
            targets_data = payload.get("targets", [])
            for tgt_data in targets_data:
                targets.append(self._parse_vessel(tgt_data))

            # парсим окружающую среду
            env_data = payload.get("environment", {})
            vis_str = env_data.get("visibility", "GOOD")
            try:
                vis = Visibility[vis_str]
            except KeyError:
                vis = Visibility.GOOD

            env = Environment(
                visibility=vis,
                in_narrow_channel=bool(env_data.get("in_narrow_channel", False)),
                in_tss=bool(env_data.get("in_tss", False)),
            )

            wind_direction = payload.get("wind_direction")
            if wind_direction is not None:
                wind_direction = float(wind_direction)

            # выполняем оценку
            decision = self.engine.evaluate(
                own, targets, env, wind_direction=wind_direction
            )

            # формируем ответ
            target_decisions_serializable = {}
            for name, tgt_dec in decision.target_decisions.items():
                target_decisions_serializable[name] = {
                    "target_name": tgt_dec.target_name,
                    "collision_risk": tgt_dec.collision_risk,
                    "encounter_type": tgt_dec.encounter_type,
                    "own_role": tgt_dec.own_role.value,
                    "recommended_action": tgt_dec.recommended_action.value,
                    "cpa": tgt_dec.cpa,
                    "tcpa": tgt_dec.tcpa,
                    "explanation": tgt_dec.explanation,
                }

            response = {
                "request_id": request_id,
                "status": "success",
                "collision_risk": decision.collision_risk,
                "own_role": decision.own_role.value,
                "recommended_action": decision.recommended_action.value,
                "recommended_heading": decision.recommended_heading,
                "forbidden_sectors": decision.forbidden_sectors,
                "maneuver_possible": decision.maneuver_possible,
                "target_decisions": target_decisions_serializable,
                "explanation": decision.explanation,
            }

            self.client.publish(MQTT_TOPIC_RESULT, json.dumps(response))
            logger.info(
                f"[{request_id}] Оценка завершена. Решение опубликовано в {MQTT_TOPIC_RESULT}"
            )

        except Exception as e:
            logger.error(f"[{request_id}] Ошибка при расчете расхождения: {e}")
            self._publish_error(request_id, str(e))

    def _publish_error(self, request_id: str, error_message: str) -> None:
        response = {
            "request_id": request_id,
            "status": "error",
            "message": error_message,
        }
        self.client.publish(MQTT_TOPIC_RESULT, json.dumps(response))

    def start(self):
        try:
            logger.info("Подключение к MQTT-брокеру...")
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self.client.loop_forever()
        except KeyboardInterrupt:
            logger.info("Отключение от MQTT-брокера...")
            self.client.disconnect()
        except Exception as e:
            logger.error(f"Не удалось запустить экспертный MQTT-узел: {e}")


if __name__ == "__main__":
    node = ExpertNode()
    node.start()
