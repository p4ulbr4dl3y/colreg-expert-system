import json

import paho.mqtt.client as mqtt

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_COMMAND = "colreg/expert/command"
MQTT_TOPIC_RESULT = "colreg/expert/result"


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print("подключено к MQTT-брокеру.")
        client.subscribe(MQTT_TOPIC_RESULT)
        print(f"подписан на топик результатов: {MQTT_TOPIC_RESULT}")

        # симулируем ситуацию пересечения и встречного сближения одновременно
        test_msg = {
            "request_id": "sim-req-101",
            "action": "evaluate",
            "own_ship": {
                "name": "OwnShip_Vessel",
                "x": 0.0,
                "y": 0.0,
                "course": 0.0,
                "speed": 12.0,
                "vessel_type": "POWER_DRIVEN",
                "min_turning_radius": 0.25,
            },
            "targets": [
                {
                    "name": "TargetA_Starboard",
                    "x": 1.2,
                    "y": 1.2,
                    "course": 270.0,
                    "speed": 10.0,
                    "vessel_type": "POWER_DRIVEN",
                },
                {
                    "name": "TargetB_HeadOn",
                    "x": 0.0,
                    "y": 2.5,
                    "course": 180.0,
                    "speed": 10.0,
                    "vessel_type": "POWER_DRIVEN",
                },
            ],
            "environment": {
                "visibility": "GOOD",
                "in_narrow_channel": False,
                "in_tss": False,
            },
        }

        print(f"отправка команды оценки обстановки в топик {MQTT_TOPIC_COMMAND}...")
        client.publish(MQTT_TOPIC_COMMAND, json.dumps(test_msg))
    else:
        print(f"ошибка подключения: {reason_code}")


def on_message(client, userdata, msg):
    print(f"\nполучен ответ от экспертной системы, топик: {msg.topic}")
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"ошибка парсинга ответа: {e}")
        print(f"сырые данные: {msg.payload}")
    print("\nсимуляция успешно завершена!")
    client.disconnect()


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "test_navigation_computer")
client.on_connect = on_connect
client.on_message = on_message

print("подключение к брокеру...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_forever()
