import sys
from src.models import Vessel, VesselType, Visibility, Environment, Action, VesselRole
from src.engine import COLREGInferenceEngine

def print_decision(own: Vessel, targets: list[Vessel], env: Environment, wind_dir: float = None):
    engine = COLREGInferenceEngine()
    decision = engine.evaluate(own, targets, env, wind_direction=wind_dir)
    
    print("=" * 70)
    print(" СОСТОЯНИЕ СОБСТВЕННОГО СУДНА:")
    print(f"  Имя: {own.name} | Тип: {own.vessel_type.description_ru()}")
    print(f"  Координаты: ({own.x:.2f}, {own.y:.2f}) | Курс: {own.course}° | Скорость: {own.speed} уз.")
    print(f"  Радиус циркуляции: {own.min_turning_radius:.2f} миль")
    
    print("-" * 70)
    print(" СОСТОЯНИЕ ЦЕЛЕЙ:")
    for tgt in targets:
        print(f"  Цель [{tgt.name}]: {tgt.vessel_type.description_ru()}")
        print(f"    Координаты: ({tgt.x:.2f}, {tgt.y:.2f}) | Курс: {tgt.course}° | Скорость: {tgt.speed} уз.")
    
    print("-" * 70)
    print(" ОКРУЖАЮЩАЯ СРЕДА:")
    visibility_str = "Ограниченная из-за тумана или осадков" if env.visibility == Visibility.RESTRICTED else "Хорошая, когда суда находятся на виду друг у друга"
    print(f"  Видимость: {visibility_str}")
    if wind_dir is not None:
        print(f"  Направление ветра: {wind_dir}°")
        
    print("-" * 70)
    print(" РЕШЕНИЕ ЭКСПЕРТНОЙ СИСТЕМЫ:")
    risk_str = "ОПАСНОСТЬ СТОЛКНОВЕНИЯ!" if decision.collision_risk else "БЕЗОПАСНО"
    print(f"  Статус: {risk_str}")
    print(f"  Общая роль нашего судна: {decision.own_role.description_ru()}")
    print(f"  Рекомендуемое действие: {decision.recommended_action.description_ru()}")
    if decision.recommended_heading is not None:
        print(f"  Рекомендуемый новый курс: {decision.recommended_heading:.1f}°")
    
    print("-" * 70)
    print(" ПОДРОБНЫЙ ВЫВОД И ОБОСНОВАНИЕ:")
    for line in decision.explanation:
        print(f"  {line}")
    print("=" * 70)
    print()

def run_predefined_scenarios():
    print("Запуск предустановленных навигационных сценариев...\n")
    
    # Сценарий 1: Сложный случай, 2 опасные цели одновременно
    print("Сценарий 1: многоцелевой конфликт, пересечение и встречное судно")
    print("  - Наше судно идет курсом 0°")
    print("  - Цель A: справа, пересекает курс слева направо")
    print("  - Цель B: встречная, идет прямо на нас")
    own = Vessel("OwnShip", 0, 0, 0, 12, VesselType.POWER_DRIVEN, min_turning_radius=0.25)
    target_a = Vessel("TargetA", 1.2, 1.2, 270, 10, VesselType.POWER_DRIVEN)
    target_b = Vessel("TargetB", 0.0, 2.5, 180, 10, VesselType.POWER_DRIVEN)
    env = Environment(visibility=Visibility.GOOD)
    print_decision(own, [target_a, target_b], env)
    
    # Сценарий 2: Физическое ограничение маневра
    print("Сценарий 2: ограничение маневренности")
    print("  - Встречное судно появилось прямо по курсу очень близко")
    print("  - Из-за высокой скорости и большого радиуса циркуляции мы физически не успеем развернуться")
    own_heavy = Vessel("OwnShip_heavy", 0, 0, 0, 20, VesselType.POWER_DRIVEN, min_turning_radius=0.8)
    target_close = Vessel("TargetShip_close", 0.0, 0.3, 180, 10, VesselType.POWER_DRIVEN)
    print_decision(own_heavy, [target_close], env)

    # Сценарий 3: Разные приоритеты судов
    print("Сценарий 3: расхождение с парусным судном и рыболовным судном")
    print("  - Мы - моторное судно. Слева идет парусное судно, справа - рыболовное.")
    print("  - Мы уступаем обоим.")
    own_power = Vessel("OwnShip_power", 0, 0, 0, 12, VesselType.POWER_DRIVEN)
    target_sail = Vessel("TargetSail", -1.0, 1.0, 90, 6, VesselType.SAILING)
    target_fish = Vessel("TargetFish", 1.0, 1.0, 270, 6, VesselType.FISHING)
    print_decision(own_power, [target_sail, target_fish], env)

def get_vessel_type_input(prompt: str) -> VesselType:
    print(prompt)
    types = list(VesselType)
    for i, t in enumerate(types):
        suffix = "." if i == len(types) - 1 else ";"
        print(f"- {i + 1}: {t.description_ru()}{suffix}")
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
    own_name = input("Имя нашего судна [по умолчанию: OwnShip]: ").strip() or "OwnShip"
    own_type = get_vessel_type_input("Тип собственного судна:")
    own_course = get_float_input("Курс собственного судна (от 0 до 360°)", 0.0) % 360
    own_speed = get_float_input("Скорость собственного судна (узлы)", 12.0)
    own_radius = get_float_input("Радиус циркуляции (обычно от 0.2 до 0.5 миль)", 0.25)
    
    own = Vessel(own_name, 0, 0, own_course, own_speed, own_type, min_turning_radius=own_radius)
    
    targets = []
    num_targets = int(get_float_input("Сколько судов-целей добавить?", 1))
    
    for i in range(num_targets):
        print(f"\n[Судно-цель {i + 1}]")
        name = input(f"Имя цели {i + 1} [по умолчанию: Target_{i + 1}]: ").strip() or f"Target_{i + 1}"
        tgt_type = get_vessel_type_input(f"Тип цели {name}:")
        tgt_x = get_float_input(f"Координата X для {name} (в милях относительно нас, +Восток)", 1.0)
        tgt_y = get_float_input(f"Координата Y для {name} (в милях относительно нас, +Север)", 1.0)
        tgt_course = get_float_input(f"Курс {name} (от 0 до 360°)", 270.0) % 360
        tgt_speed = get_float_input(f"Скорость {name} (узлы)", 10.0)
        
        targets.append(Vessel(name, tgt_x, tgt_y, tgt_course, tgt_speed, tgt_type))
    
    print("\n[Окружающая среда]")
    print("Видимость:")
    print("- 1: хорошая видимость, когда суда находятся на виду друг у друга;")
    print("- 2: ограниченная видимость из-за тумана или осадков.")
    vis_choice = input("Выберите видимость (1 или 2) [по умолчанию 1]: ").strip()
    vis = Visibility.GOOD if vis_choice != "2" else Visibility.RESTRICTED
    
    wind_dir = None
    # Если есть хотя бы два парусных судна, спрашиваем про ветер
    sailing_count = (1 if own_type == VesselType.SAILING else 0) + sum(1 for t in targets if t.vessel_type == VesselType.SAILING)
    if sailing_count >= 2:
        wind_dir = get_float_input("Обнаружены парусные суда. Введите направление ветра (от 0 до 360°)", 0.0)
        
    env = Environment(visibility=vis)
    
    print("\nРезультаты расчетов экспертной системы:")
    print_decision(own, targets, env, wind_dir)

def main():
    print("=" * 70)
    print(" ЭКСПЕРТНАЯ СИСТЕМА ПРЕДУПРЕЖДЕНИЯ СТОЛКНОВЕНИЙ СУДОВ - ВЕРСИЯ ПРОДАКШН")
    print("=" * 70)
    
    while True:
        print("Меню:")
        print("- 1: запустить стандартные сценарии расхождения;")
        print("- 2: задать свой сценарий расхождения;")
        print("- 3: выход.")
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
