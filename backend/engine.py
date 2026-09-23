"""Deterministic HackAlem city-simulation rules and scoring."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import Any


HORIZON = 8
BUDGET = 100
INDICATORS = {
    "T1": {"name": "Разгрузка дорог", "direction": "Транспорт", "weight": 0.10},
    "T2": {"name": "Доступность общественного транспорта", "direction": "Транспорт", "weight": 0.10},
    "E1": {"name": "Озеленение", "direction": "Экология", "weight": 0.09},
    "E2": {"name": "Качество воздуха", "direction": "Экология", "weight": 0.11},
    "S1": {"name": "Школы и детсады", "direction": "Соцсфера", "weight": 0.11},
    "S2": {"name": "Поликлиники и первичная медпомощь", "direction": "Соцсфера", "weight": 0.11},
    "B1": {"name": "Безопасность улиц", "direction": "Безопасность", "weight": 0.09},
    "B2": {"name": "Безопасность дорожного движения", "direction": "Безопасность", "weight": 0.09},
    "C1": {"name": "Надёжность ЖКХ", "direction": "Сервисы", "weight": 0.10},
    "C2": {"name": "Скорость решения обращений", "direction": "Сервисы", "weight": 0.10},
}

DISTRICTS = {
    "esil": {"name": "Есиль", "population": 0.27, "profile": "Богатый район, но с пробками на мостах и переполненными школами.", "indicators": {"T1": 45, "T2": 62, "E1": 68, "E2": 72, "S1": 48, "S2": 55, "B1": 78, "B2": 60, "C1": 75, "C2": 70}},
    "almaty": {"name": "Алматы", "population": 0.24, "profile": "Старый ЖКХ и пробки.", "indicators": {"T1": 40, "T2": 75, "E1": 50, "E2": 55, "S1": 60, "S2": 65, "B1": 62, "B2": 52, "C1": 50, "C2": 60}},
    "saryarka": {"name": "Сарыарка", "population": 0.20, "profile": "Смог от частного сектора, слабое озеленение.", "indicators": {"T1": 50, "T2": 70, "E1": 42, "E2": 40, "S1": 62, "S2": 68, "B1": 58, "B2": 55, "C1": 45, "C2": 55}},
    "baykonur": {"name": "Байконур", "population": 0.13, "profile": "Середняк без ярких перекосов.", "indicators": {"T1": 52, "T2": 68, "E1": 55, "E2": 50, "S1": 58, "S2": 60, "B1": 52, "B2": 58, "C1": 55, "C2": 58}},
    "nura": {"name": "Нура", "population": 0.16, "profile": "Главный аутсайдер по соцсфере и транспорту.", "indicators": {"T1": 55, "T2": 40, "E1": 45, "E2": 65, "S1": 38, "S2": 35, "B1": 55, "B2": 50, "C1": 60, "C2": 50}},
}

MEASURES = {
    "M1": {"name": "Выделенные полосы для автобусов", "direction": "Транспорт", "type": "Район", "cost": 18, "lag": 2, "effects": {"T1": 6, "T2": 9}, "description": "Выделенные полосы делают автобусные маршруты быстрее и надёжнее."},
    "M2": {"name": "Умные светофоры (адаптивное управление)", "direction": "Транспорт", "type": "Город", "cost": 22, "lag": 2, "effects": {"T1": 4, "B2": 3}, "description": "Светофоры адаптируют фазы к потоку транспорта и снижают задержки."},
    "M3": {"name": "Линия ЛРТ / расширение", "direction": "Транспорт", "type": "Район", "cost": 30, "lag": 4, "effects": {"T1": 16, "T2": 20, "E2": 4}, "description": "Расширение скоростного транспорта повышает доступность поездок, но начинает работать позже."},
    "M4": {"name": "Парк / сквер", "direction": "Экология", "type": "Район", "cost": 15, "lag": 2, "effects": {"E1": 12, "E2": 3, "B1": 2}, "description": "Новый зелёный участок улучшает экологию и качество общественного пространства."},
    "M5": {"name": "Перевод частного сектора на чистое топливо", "direction": "Экология", "type": "Район", "cost": 25, "lag": 3, "effects": {"E2": 14, "C1": 4}, "description": "Переход на более чистое топливо снижает загрязнение воздуха и помогает инфраструктуре."},
    "M6": {"name": "Городская программа озеленения и ветрозащитных полос", "direction": "Экология", "type": "Город", "cost": 20, "lag": 4, "effects": {"E1": 5, "E2": 3}, "description": "Городская программа расширяет зелёные зоны и помогает уменьшать пыль."},
    "M7": {"name": "Школа + детсад (модульное строительство)", "direction": "Соцсфера", "type": "Район", "cost": 24, "lag": 3, "effects": {"S1": 16}, "description": "Модульные школа и детский сад увеличивают доступность мест для семей."},
    "M8": {"name": "Центр семейного здоровья / поликлиника", "direction": "Соцсфера", "type": "Район", "cost": 20, "lag": 3, "effects": {"S2": 14}, "description": "Новый центр первичной помощи сокращает нехватку медицинской инфраструктуры."},
    "M9": {"name": "Дворовые спорт-хабы", "direction": "Соцсфера", "type": "Район", "cost": 10, "lag": 1, "effects": {"S1": 3, "S2": 3, "B1": 3}, "description": "Спортивные площадки создают доступные места для досуга и активности рядом с домом."},
    "M10": {"name": "Освещение и камеры (расширение Safe City)", "direction": "Безопасность", "type": "Район", "cost": 12, "lag": 1, "effects": {"B1": 12, "B2": 2}, "description": "Освещение и камеры повышают безопасность улиц и дорожных перемещений."},
    "M11": {"name": "Безопасные переходы и школьные зоны", "direction": "Безопасность", "type": "Район", "cost": 10, "lag": 1, "effects": {"B2": 12, "T1": -2}, "description": "Безопасные переходы снижают риск ДТП; отдельные ограничения могут замедлить поток."},
    "M12": {"name": "Единая цифровая платформа обращений", "direction": "Сервисы", "type": "Город", "cost": 14, "lag": 1, "effects": {"C2": 5}, "description": "Единая платформа помогает быстрее разбирать обращения жителей."},
    "M13": {"name": "Модернизация тепло- и водосетей", "direction": "Сервисы", "type": "Район", "cost": 28, "lag": 4, "effects": {"C1": 18, "E2": 2}, "description": "Обновление сетей снижает вероятность коммунальных аварий, но эффект развивается постепенно."},
    "M14": {"name": "Аварийные бригады ЖКХ + раннее оповещение", "direction": "Сервисы", "type": "Город", "cost": 16, "lag": 1, "effects": {"C1": 5, "C2": 2}, "description": "Оперативные бригады и оповещение помогают быстрее реагировать на сбои ЖКХ."},
}

SYNERGIES = [
    {"measures": ["M1", "M2"], "indicator": "T1", "bonus": 2, "district_measure": "M1", "description": "Умные светофоры поддерживают эффект автобусных полос."},
    {"measures": ["M10", "M12"], "indicator": "B1", "bonus": 2, "district_measure": "M10", "description": "Цифровая платформа дополняет систему безопасности."},
    {"measures": ["M5", "M6"], "indicator": "E2", "bonus": 2, "district_measure": "M5", "description": "Чистое топливо усиливается городской экологической программой."},
]
CONFLICTS = [
    {"measures": ["M1", "M3"], "same_district": False, "reason": "Либо выделенные автобусные полосы, либо ЛРТ."},
    {"measures": ["M4", "M7"], "same_district": True, "reason": "Конфликт за участок: парк и школа не могут занять одну площадку."},
    {"measures": ["M5", "M13"], "same_district": True, "reason": "Дублирование программ в одном районе."},
]


class RuleViolation(ValueError):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _conflict_reason(first: dict[str, Any], second: dict[str, Any]) -> str | None:
    for rule in CONFLICTS:
        a, b = rule["measures"]
        if {first["measure_id"], second["measure_id"]} != {a, b}:
            continue
        if rule["same_district"] and first.get("district_id") != second.get("district_id"):
            continue
        return rule["reason"]
    return None


def validate_decisions(decisions: list[dict[str, Any]], require_five: bool = True) -> None:
    if require_five and len(decisions) != 5:
        raise RuleViolation("Нужно принять ровно 5 решений.")
    if len(decisions) > 5:
        raise RuleViolation("Лимит — ровно 5 решений.")
    spent = 0
    direction_count: Counter[str] = Counter()
    seen: set[str] = set()
    for i, decision in enumerate(decisions):
        measure_id = decision.get("measure_id")
        if measure_id not in MEASURES:
            raise RuleViolation(f"Решение {i + 1}: неизвестная мера.")
        measure = MEASURES[measure_id]
        if measure_id in seen:
            raise RuleViolation(f"Меру {measure_id} нельзя выбрать повторно.")
        seen.add(measure_id)
        district_id = decision.get("district_id")
        if measure["type"] == "Район" and district_id not in DISTRICTS:
            raise RuleViolation(f"Для меры «{measure['name']}» обязательно выберите район.")
        if measure["type"] == "Город" and district_id is not None:
            raise RuleViolation(f"Мера «{measure['name']}» действует на весь город — район не указывается.")
        spent += measure["cost"]
        direction_count[measure["direction"]] += 1
        if direction_count[measure["direction"]] > 2:
            raise RuleViolation(f"Можно выбрать не больше двух мер направления «{measure['direction']}».")
        for earlier in decisions[:i]:
            reason = _conflict_reason(decision, earlier)
            if reason:
                raise RuleViolation(f"Конфликт между {measure_id} и {earlier['measure_id']}: {reason}")
    if spent > BUDGET:
        raise RuleViolation(f"Не хватает бюджета: стоимость плана {spent}, бюджет {BUDGET}.")


def _district_score(indicators: dict[str, float]) -> float:
    return sum(indicators[key] * meta["weight"] for key, meta in INDICATORS.items())


def calculate(decisions: list[dict[str, Any]], require_five: bool = True) -> dict[str, Any]:
    validate_decisions(decisions, require_five=require_five)
    initial = {key: deepcopy(district["indicators"]) for key, district in DISTRICTS.items()}
    updated = deepcopy(initial)
    applied: list[dict[str, Any]] = []
    spent = 0
    directions: Counter[str] = Counter()

    for decision in decisions:
        measure_id = decision["measure_id"]
        measure = MEASURES[measure_id]
        district_id = decision.get("district_id")
        factor = (HORIZON - measure["lag"]) / HORIZON
        affected_districts = [district_id] if district_id else list(DISTRICTS)
        spent += measure["cost"]
        directions[measure["direction"]] += 1
        for target in affected_districts:
            for indicator, amount in measure["effects"].items():
                updated[target][indicator] += amount * factor
        applied.append({"measure_id": measure_id, "district_id": district_id, "cost": measure["cost"], "lag": measure["lag"], "realized_factor": factor, "affected_districts": affected_districts})

    active_synergies = []
    chosen = {decision["measure_id"]: decision for decision in decisions}
    for synergy in SYNERGIES:
        a, b = synergy["measures"]
        if a not in chosen or b not in chosen:
            continue
        target = chosen[synergy["district_measure"]]["district_id"]
        if target is None:
            continue
        updated[target][synergy["indicator"]] += synergy["bonus"]
        active_synergies.append({**synergy, "district_id": target})

    for district_id in updated:
        for indicator, value in updated[district_id].items():
            updated[district_id][indicator] = min(100.0, max(0.0, value))

    district_results = {}
    critical_count = 0
    for district_id, district in DISTRICTS.items():
        score_before = _district_score(initial[district_id])
        score_after = _district_score(updated[district_id])
        critical = [key for key, value in updated[district_id].items() if value < 40]
        critical_count += len(critical)
        district_results[district_id] = {
            "name": district["name"],
            "population": district["population"],
            "profile": district["profile"],
            "score_before": score_before,
            "score_after": score_after,
            "score_delta": score_after - score_before,
            "initial": initial[district_id],
            "final": updated[district_id],
            "critical_indicators": critical,
        }

    city_before = sum(DISTRICTS[key]["population"] * district_results[key]["score_before"] for key in DISTRICTS)
    city_after = sum(DISTRICTS[key]["population"] * district_results[key]["score_after"] for key in DISTRICTS)
    weakest_before = min(item["score_before"] for item in district_results.values())
    weakest_after = min(item["score_after"] for item in district_results.values())
    baseline_criticals = sum(1 for d in initial.values() for value in d.values() if value < 40)
    baseline_score = 0.7 * city_before + 0.3 * weakest_before - baseline_criticals
    final_score = 0.7 * city_after + 0.3 * weakest_after - critical_count
    indicator_deltas = {
        district_id: {key: updated[district_id][key] - initial[district_id][key] for key in INDICATORS}
        for district_id in DISTRICTS
    }

    return {
        "budget": BUDGET,
        "spent": spent,
        "remaining": BUDGET - spent,
        "decisions_count": len(decisions),
        "simulation_complete": len(decisions) == 5,
        "horizon_quarters": HORIZON,
        "baseline_score": baseline_score,
        "final_score": final_score,
        "score_delta": final_score - baseline_score,
        "city_score_before": city_before,
        "city_score_after": city_after,
        "weakest_district_before": min(district_results, key=lambda key: district_results[key]["score_before"]),
        "weakest_district_after": min(district_results, key=lambda key: district_results[key]["score_after"]),
        "critical_count_before": baseline_criticals,
        "critical_count_after": critical_count,
        "districts": district_results,
        "indicators": INDICATORS,
        "indicator_deltas": indicator_deltas,
        "measures": [{**entry, **MEASURES[entry["measure_id"]]} for entry in applied],
        "synergies": active_synergies,
        "direction_counts": dict(directions),
    }


def public_dataset() -> dict[str, Any]:
    return {
        "budget": BUDGET,
        "horizon_quarters": HORIZON,
        "baseline_score": 52.56,
        "districts": DISTRICTS,
        "indicators": INDICATORS,
        "measures": MEASURES,
        "synergies": SYNERGIES,
        "conflicts": CONFLICTS,
    }
