import json
import unittest
from unittest.mock import MagicMock, patch
from scripts.mqtt_node import ExpertNode
from src.models import VesselRole, Action

class TestMQTTNode(unittest.TestCase):
    @patch("scripts.mqtt_node.mqtt.Client")
    def setUp(self, mock_client_cls):
        # Мокаем клиент MQTT при инициализации
        self.mock_client = MagicMock()
        mock_client_cls.return_value = self.mock_client
        self.node = ExpertNode()

    def test_evaluate_command_processing(self):
        # Имитируем входящее сообщение от радара/АИС
        payload = {
            "request_id": "test-mqtt-123",
            "action": "evaluate",
            "own_ship": {
                "name": "OwnShip",
                "x": 0.0,
                "y": 0.0,
                "course": 0.0,
                "speed": 10.0,
                "vessel_type": "POWER_DRIVEN"
            },
            "targets": [
                {
                    "name": "TargetShip",
                    "x": 0.0,
                    "y": 1.5,
                    "course": 180.0,
                    "speed": 10.0,
                    "vessel_type": "POWER_DRIVEN"
                }
            ],
            "environment": {
                "visibility": "GOOD"
            }
        }
        
        # Создаем мок сообщения MQTT
        mock_msg = MagicMock()
        mock_msg.topic = "colreg/expert/command"
        mock_msg.payload = json.dumps(payload).encode("utf-8")
        
        # Передаем сообщение в обработчик
        self.node._on_message(self.mock_client, None, mock_msg)
        
        # Проверяем, что ответ был отправлен в топик результатов
        self.mock_client.publish.assert_called_once()
        call_args = self.mock_client.publish.call_args
        
        topic = call_args[0][0]
        payload_sent = json.loads(call_args[0][1])
        
        self.assertEqual(topic, "colreg/expert/result")
        self.assertEqual(payload_sent["request_id"], "test-mqtt-123")
        self.assertEqual(payload_sent["status"], "success")
        self.assertTrue(payload_sent["collision_risk"])
        self.assertEqual(payload_sent["own_role"], VesselRole.GIVE_WAY.value)
        self.assertEqual(payload_sent["recommended_action"], Action.ALTER_COURSE_STARBOARD.value)
        self.assertIsNotNone(payload_sent["recommended_heading"])

    @patch("scripts.mqtt_node.mqtt.Client")
    def test_invalid_json(self, mock_client_cls):
        # Отправка невалидного JSON
        mock_msg = MagicMock()
        mock_msg.payload = b"invalid json"
        
        # Обработка не должна падать с ошибкой, а должна логировать её
        try:
            self.node._on_message(self.mock_client, None, mock_msg)
        except Exception as e:
            self.fail(f"Handler raised exception on invalid json: {e}")

if __name__ == "__main__":
    unittest.main()
