import json
import os
import signal
import socket
import subprocess
import time
import unittest


def is_port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0


class TestWebDashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.managed_processes = []

        # 1. Запуск MQTT-брокера, если он не запущен на стандартных портах
        if not is_port_open(1883) and not is_port_open(9001):
            print("Starting MQTT Broker...")
            broker = subprocess.Popen(
                ["uv", "run", "amqtt", "-c", "scripts/amqtt.yaml"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd="/Users/yegor/expert-system",
            )
            cls.managed_processes.append(broker)
            time.sleep(2.0)

        # 2. Запуск экспертного узла, если он не запущен
        try:
            subprocess.check_output(["pgrep", "-f", "mqtt_node.py"])
            node_running = True
        except subprocess.CalledProcessError:
            node_running = False

        if not node_running:
            print("Starting Expert Node...")
            node = subprocess.Popen(
                ["uv", "run", "scripts/mqtt_node.py"],
                cwd="/Users/yegor/expert-system",
            )
            cls.managed_processes.append(node)
            time.sleep(1.0)

        # 3. Запуск HTTP-сервера, если он не запущен
        if not is_port_open(8000):
            print("Starting HTTP Server...")
            server = subprocess.Popen(
                ["python3", "-m", "http.server", "--directory", "web", "8000"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd="/Users/yegor/expert-system",
            )
            cls.managed_processes.append(server)
            time.sleep(1.0)

        # 4. Открытие страницы в браузере
        print("Opening dashboard in browser...")
        subprocess.run(
            ["agent-browser", "open", "http://localhost:8000"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        time.sleep(2.0)  # Ожидание установления соединения MQTT на странице

    @classmethod
    def tearDownClass(cls):
        # Остановка всех запущенных процессов
        for p in cls.managed_processes:
            try:
                p.terminate()
                p.wait(timeout=2.0)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    def _eval_js(self, code):
        res = subprocess.run(
            ["agent-browser", "eval", code], capture_output=True, text=True, check=True
        )
        val = res.stdout.strip()
        if (
            (val.startswith('"') and val.endswith('"'))
            or (val.startswith("{") and val.endswith("}"))
            or (val.startswith("[") and val.endswith("]"))
        ):
            try:
                return json.loads(val)
            except Exception:
                pass
        return val

    def _click_preset(self, num):
        self._eval_js(f'document.getElementById("preset{num}").click()')
        time.sleep(0.8)  # Ожидание завершения цикла приема-передачи сообщения

    def test_preset_1_multi_target(self):
        """Тестирование пресета 1: опасность столкновения с несколькими целями."""
        self._click_preset(1)
        state = self._eval_js(
            'JSON.stringify({risk: document.getElementById("riskBadge").textContent, role: document.getElementById("vesselRoleText").textContent, action: document.getElementById("actionText").textContent, heading: document.getElementById("headingText").textContent, warning: document.getElementById("warningBox").style.display})'
        )
        state_dict = json.loads(state)

        self.assertEqual(state_dict["risk"], "опасность столкновения!")
        self.assertEqual(state_dict["role"], "судно, уступающее дорогу")
        self.assertEqual(
            state_dict["action"], "изменить курс вправо (на правый борт)"
        )
        self.assertEqual(state_dict["heading"], "105.0°")
        self.assertEqual(state_dict["warning"], "none")

    def test_preset_2_maneuver_limit(self):
        """Тестирование пресета 2: физические ограничения маневренности."""
        self._click_preset(2)
        state = self._eval_js(
            'JSON.stringify({risk: document.getElementById("riskBadge").textContent, role: document.getElementById("vesselRoleText").textContent, action: document.getElementById("actionText").textContent, heading: document.getElementById("headingText").textContent, warning: document.getElementById("warningBox").style.display})'
        )
        state_dict = json.loads(state)

        self.assertEqual(state_dict["risk"], "опасность столкновения!")
        self.assertEqual(state_dict["role"], "судно, уступающее дорогу")
        self.assertEqual(
            state_dict["action"], "изменить курс влево (на левый борт)"
        )
        self.assertEqual(state_dict["heading"], "239.0°")
        self.assertIn(state_dict["warning"], ["flex", "block"])

    def test_preset_3_priorities(self):
        """Тестирование пресета 3: иерархия приоритетов судов."""
        self._click_preset(3)
        state = self._eval_js(
            'JSON.stringify({risk: document.getElementById("riskBadge").textContent, role: document.getElementById("vesselRoleText").textContent, action: document.getElementById("actionText").textContent, heading: document.getElementById("headingText").textContent, warning: document.getElementById("warningBox").style.display})'
        )
        state_dict = json.loads(state)

        self.assertEqual(state_dict["risk"], "опасность столкновения!")
        self.assertEqual(state_dict["role"], "судно, уступающее дорогу")
        self.assertEqual(
            state_dict["action"], "изменить курс вправо (на правый борт)"
        )
        self.assertEqual(state_dict["heading"], "103.0°")
        self.assertEqual(state_dict["warning"], "none")

    def test_preset_4_restricted_visibility(self):
        """Тестирование пресета 4: правила расхождения при ограниченной видимости."""
        self._click_preset(4)
        state = self._eval_js(
            'JSON.stringify({risk: document.getElementById("riskBadge").textContent, role: document.getElementById("vesselRoleText").textContent, action: document.getElementById("actionText").textContent, heading: document.getElementById("headingText").textContent, warning: document.getElementById("warningBox").style.display})'
        )
        state_dict = json.loads(state)

        self.assertEqual(state_dict["risk"], "опасность столкновения!")
        self.assertEqual(state_dict["role"], "судно, уступающее дорогу")
        self.assertEqual(
            state_dict["action"], "изменить курс вправо (на правый борт)"
        )
        self.assertEqual(state_dict["heading"], "105.0°")
        self.assertIn(state_dict["warning"], ["flex", "block"])

    def test_manual_interaction_priority(self):
        """Тестирование ручного изменения параметров судна и обновления состояния."""
        # Клик на пресет 3
        self._click_preset(3)

        # Изменение типа собственного судна на судно, лишенное возможности управляться, и скорости на 2 узла
        self._eval_js(
            'document.getElementById("ownType").value = "NUC"; document.getElementById("ownType").dispatchEvent(new Event("change"));'
        )
        self._eval_js(
            'document.getElementById("ownSpeed").value = 2; document.getElementById("ownSpeed").dispatchEvent(new Event("input"));'
        )
        time.sleep(0.8)

        state = self._eval_js(
            'JSON.stringify({risk: document.getElementById("riskBadge").textContent, role: document.getElementById("vesselRoleText").textContent})'
        )
        state_dict = json.loads(state)

        # Собственное судно должно получить статус судна, которому уступают дорогу
        self.assertEqual(state_dict["risk"], "опасность столкновения!")
        self.assertEqual(state_dict["role"], "судно, которому уступают дорогу")


if __name__ == "__main__":
    unittest.main()
