#!/bin/bash

# Функция для остановки фоновых процессов при выходе
cleanup() {
    echo ""
    echo "Останавливаем фоновые процессы..."
    kill "$BROKER_PID" "$NODE_PID" "$SERVER_PID" 2>/dev/null
    exit 0
}

# Перехватываем Ctrl+C для очистки ресурсов
trap cleanup INT TERM

echo "Запуск MQTT-брокера..."
uv run amqtt -c scripts/amqtt.yaml > /dev/null 2>&1 &
BROKER_PID=$!

# Даем брокеру время на инициализацию
sleep 1.5

echo "Запуск узла экспертной системы..."
uv run scripts/mqtt_node.py &
NODE_PID=$!

echo "Запуск веб-сервера на порту 8000..."
python3 -m http.server --directory web 8000 > /dev/null 2>&1 &
SERVER_PID=$!

# Даем веб-серверу время на запуск
sleep 0.5

echo "Открываем панель визуализации в браузере..."
open http://localhost:8000

echo "Инфраструктура успешно запущена. Для остановки нажмите Ctrl+C."

# Ожидаем завершения фоновых процессов
wait
