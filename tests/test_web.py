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

        # 1. Start MQTT Broker if not running on standard ports
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

        # 2. Start Expert Node if not running
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

        # 3. Start HTTP Server if not running
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

        # 4. Open page in agent-browser
        print("Opening dashboard in browser...")
        subprocess.run(
            ["agent-browser", "open", "http://localhost:8000"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        time.sleep(2.0)  # Wait for MQTT connection inside the browser page

    @classmethod
    def tearDownClass(cls):
        # Stop all processes we started
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
        time.sleep(0.8)  # wait for MQTT roundtrip

    def test_preset_1_multi_target(self):
        """Test Preset 1: Multi-target collision risk."""
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
        """Test Preset 2: Physical maneuverability limitation."""
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
        """Test Preset 3: Vessel priority hierarchy (Sailing & Fishing)."""
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
        """Test Preset 4: Restricted visibility encounter rules (Rule 19)."""
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
        """Test manually changing own vessel parameters and updating the UI state."""
        # Click Preset 3 (priorities, good visibility)
        self._click_preset(3)

        # Change own vessel type to NUC (highest priority) and speed to 2 knots
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

        # We should now be the stand-on vessel
        self.assertEqual(state_dict["risk"], "опасность столкновения!")
        self.assertEqual(state_dict["role"], "судно, которому уступают дорогу")


if __name__ == "__main__":
    unittest.main()
