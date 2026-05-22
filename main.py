import sys
from src.models import Vessel, VesselType, Visibility, Environment, Action, VesselRole
from src.engine import COLREGInferenceEngine

def print_decision(own: Vessel, target: Vessel, env: Environment, wind_dir: float = None):
    engine = COLREGInferenceEngine()
    decision = engine.evaluate(own, target, env, wind_direction=wind_dir)
    
    print("=" * 60)
    print(" СОСТОЯНИЕ КОРАБЛЕЙ:")
    print(f"  Собственное судно [{own.name}]:")
    print(f"    Тип: {own.vessel_type.description_ru()}")
    print(f"    Координаты: ({own.x:.2f}, {own.y:.2f}) NM | Курс: {own.course}° | Скорость: {own.speed} уз.")
    print(f"  Судно-цель [{target.name}]:")
    print(f"    Тип: {target.vessel_type.description_ru()}")
    print(f"    Координаты: ({target.x:.2f}, {target.y:.2f}) NM | Курс: {target.course}° | Скорость: {target.speed} уз.")
    
    print("-" * 60)
    print(" ОКРУЖАЮЩАЯ СРЕДА:")
    visibility_str = "Ограниченная (туман, осадки)" if env.visibility == Visibility.RESTRICTED else "Хорошая (на виду друг у друга)"
    print(f"  Видимость: {visibility_str}")
    if wind_dir is not None:
        print(f"  Направление ветра: {wind_dir}°")
        
    print("-" * 60)
    print(" РЕШЕНИЕ ЭКСПЕРТНОЙ СИСТЕМЫ:")
    risk_str = "ОПАСНОСТЬ СТОЛКНОВЕНИЯ!" if decision.collision_risk else "БЕЗОПАСНО"
    print(f"  Статус: {risk_str}")
    print(f"  Тип сближения: {decision.encounter_type}")
    print(f"  Наша роль: {decision.own_role.description_ru()}")
    print(f"  Рекомендуемое действие: {decision.recommended_action.description_ru()}")
    
    print("-" * 60)
    print(" ОБОСНОВАНИЕ (ВЫВОДЫ ЭКСПЕРТНОЙ СИСТЕМЫ):")
    for line in decision.explanation:
        print(f"  {line}")
    print("=" * 60)
    print()

def run_predefined_scenarios():
    print("Запуск предустановленных навигационных сценариев...\n")
    
    # Сценарий 1: Встречные курсы (Лоб-в-лоб)
    print("Сценарий 1: Встречные курсы (Правило 14)")
    own = Vessel("Наше судно", 0, 0, 0, 12, VesselType.POWER_DRIVEN)
    target = Vessel("Встречное судно", 0, 2.5, 180, 10, VesselType.POWER_DRIVEN)
    env = Environment(visibility=Visibility.GOOD)
    print_decision(own, target, env)
    
    # Сценарий 2: Пересечение (цель справа - уступаем дорогу)
    print("Сценарий 2: Пересечение курсов (Правило 15, цель справа)")
    own = Vessel("Наше судно", 0, 0, 0, 15, VesselType.POWER_DRIVEN)
    target = Vessel("Судно справа", 1.2, 1.2, 270, 12, VesselType.POWER_DRIVEN)
    env = Environment(visibility=Visibility.GOOD)
    print_decision(own, target, env)

    # Сценарий 3: Пересечение (моторное судно уступает паруснику согласно Правилу 18)
    print("Сценарий 3: Расхождение моторного судна и парусника (Правило 18)")
    own = Vessel("Наше судно (мотор)", 0, 0, 0, 14, VesselType.POWER_DRIVEN)
    target = Vessel("Парусник слева", -1.0, 1.0, 90, 6, VesselType.SAILING)
    env = Environment(visibility=Visibility.GOOD)
    print_decision(own, target, env)

    # Сценарий 4: Ограниченная видимость (цель впереди)
    print("Сценарий 4: Сближение в тумане (Правило 19, цель впереди справа)")
    own = Vessel("Наше судно", 0, 0, 0, 10, VesselType.POWER_DRIVEN)
    target = Vessel("Цель в тумане", 0.8, 0.8, 240, 12, VesselType.POWER_DRIVEN)
    env = Environment(visibility=Visibility.RESTRICTED)
    print_decision(own, target, env)

def get_vessel_type_input(prompt: str) -> VesselType:
    print(prompt)
    types = list(VesselType)
    for i, t in enumerate(types):
        print(f"  {i + 1}. {t.description_ru()} ({t.name})")
    while True:
        try:
            choice = int(input("Выберите номер: "))
            if 1 <= choice <= len(types):
                return types[choice - 1]
        except ValueError:
            pass
        print("Некорректный ввод. Попробуйте еще раз.")

def get_float_input(prompt: str, default: float) -> float:
    while True:
        val = input(f"{prompt} [по умолчанию: {default}]: ").strip()
        if not val:
            return default
        try:
            return float(val)
        except ValueError:
            print("Введите числовое значение.")

def enter_custom_scenario():
    print("\n--- ВВОД ПАРАМЕТРОВ СЦЕНАРИЯ ---")
    
    print("\n[Собственное судно]")
    own_type = get_vessel_type_input("Тип собственного судна:")
    own_course = get_float_input("Курс собственного судна (0-360°)", 0.0) % 360
    own_speed = get_float_input("Скорость собственного судна (узлы)", 12.0)
    
    print("\n[Судно-цель]")
    tgt_type = get_vessel_type_input("Тип судна-цели:")
    tgt_x = get_float_input("Координата X цели (в милях относительно нас, +Восток / -Запад)", 1.0)
    tgt_y = get_float_input("Координата Y цели (в милях относительно нас, +Север / -Юг)", 1.0)
    tgt_course = get_float_input("Курс цели (0-360°)", 270.0) % 360
    tgt_speed = get_float_input("Скорость цели (узлы)", 10.0)
    
    print("\n[Окружающая среда]")
    print("Видимость:")
    print("  1. Хорошая видимость (суда видят друг друга)")
    print("  2. Ограниченная видимость (туман/осадки)")
    vis_choice = input("Выберите видимость (1 или 2) [по умолчанию 1]: ").strip()
    vis = Visibility.GOOD if vis_choice != "2" else Visibility.RESTRICTED
    
    wind_dir = None
    if own_type == VesselType.SAILING and tgt_type == VesselType.SAILING:
        wind_dir = get_float_input("Оба судна парусные. Введите направление ветра (0-360°)", 0.0)
        
    own = Vessel("OwnShip", 0, 0, own_course, own_speed, own_type)
    target = Vessel("TargetShip", tgt_x, tgt_y, tgt_course, tgt_speed, tgt_type)
    env = Environment(visibility=vis)
    
    print("\nРезультаты расчетов:")
    print_decision(own, target, env, wind_dir)

def main():
    print("=" * 60)
    print(" ЭКСПЕРТНАЯ СИСТЕМА ПРЕДУПРЕЖДЕНИЯ СТОЛКНОВЕНИЙ СУДОВ (МППСС-72)")
    print("=" * 60)
    
    while True:
        print("Меню:")
        print("  1. Запустить стандартные сценарии расхождения (тестирование)")
        print("  2. Задать свой сценарий расхождения")
        print("  3. Выход")
        choice = input("Выберите пункт меню: ").strip()
        
        if choice == "1":
            run_predefined_scenarios()
        elif choice == "2":
            enter_custom_scenario()
        elif choice == "3":
            print("Выход из программы. Счастливого пути!")
            break
        else:
            print("Некорректный выбор. Пожалуйста, введите 1, 2 или 3.\n")

if __name__ == "__main__":
    main()
