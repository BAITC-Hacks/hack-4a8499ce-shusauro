"""Deterministic, auditable facts for the fictional press narrative layer."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .engine import BUDGET, DISTRICTS, HORIZON, INDICATORS, MEASURES, SYNERGIES, calculate, validate_decisions

OUTLETS = {
    "esil": "Есиль Вестник",
    "nura": "Нура Сегодня",
    "saryarka": "Сарыарка Times",
    "almaty": "Алматы Live",
    "baykonur": "Байконур Daily",
    "city": "Столичный Шум",
}


def build_media_context(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    validate_decisions(decisions, require_five=False)
    if not decisions:
        raise ValueError("Для газетной реакции нужно хотя бы одно решение.")
    result = calculate(decisions, require_five=False)
    spent = result["spent"]
    remaining_decisions = 5 - len(decisions)
    chosen = {decision["measure_id"] for decision in decisions}
    district_counts = Counter(d["district_id"] for d in decisions if d["district_id"])
    direction_counts = Counter(MEASURES[d["measure_id"]]["direction"] for d in decisions)
    district_values = {key: value["final"] for key, value in result["districts"].items()}
    critical = [
        {"district_id": district_id, "district": DISTRICTS[district_id]["name"], "indicator": code,
         "indicator_name": INDICATORS[code]["name"], "value": value}
        for district_id, values in district_values.items()
        for code, value in values.items() if value < 40
    ]

    feasible = []
    if remaining_decisions:
        for measure_id, measure in MEASURES.items():
            if measure_id in chosen:
                continue
            targets = list(DISTRICTS) if measure["type"] == "Район" else [None]
            for district_id in targets:
                candidate = [*decisions, {"measure_id": measure_id, "district_id": district_id}]
                try:
                    validate_decisions(candidate, require_five=False)
                except ValueError:
                    continue
                feasible.append({"measure_id": measure_id, "name": measure["name"], "cost": measure["cost"], "lag": measure["lag"], "district_id": district_id})
                break
    min_cost = min((item["cost"] for item in feasible), default=None)

    angles: list[dict[str, Any]] = []
    def add(kind: str, severity: float, facts: dict[str, Any]) -> None:
        angles.append({"type": kind, "severity": round(min(1.0, severity), 2), "facts": facts})

    for district_id, count in district_counts.items():
        if count >= 2:
            weakest = result["weakest_district_after"]
            add("district_favoritism", .78 + .04 * (count - 2), {
                "favored_district": DISTRICTS[district_id]["name"], "measures_in_district": count,
                "ignored_weak_district": DISTRICTS[weakest]["name"] if weakest != district_id else None,
                "critical_metrics": [item for item in critical if item["district_id"] == weakest],
            })
    if len([d for d in decisions if d["district_id"]]) >= 2:
        unaddressed = [item for item in critical if item["district_id"] not in district_counts]
        if unaddressed:
            by_district: dict[str, list[dict[str, Any]]] = {}
            for item in unaddressed:
                by_district.setdefault(item["district_id"], []).append(item)
            target = max(by_district, key=lambda key: len(by_district[key]))
            add("ignored_weak_district", .84, {"ignored_district": DISTRICTS[target]["name"], "critical_metrics": by_district[target]})

    last_id = decisions[-1]["measure_id"]
    last = MEASURES[last_id]
    last_district = decisions[-1]["district_id"]
    if last["cost"] >= 25:
        add("megaproject", .67, {"measure_id": last_id, "measure": last["name"], "cost": last["cost"], "budget_percent": round(last["cost"] / BUDGET * 100), "district": DISTRICTS[last_district]["name"] if last_district else "город", "lag": last["lag"]})
    long_projects = [{"measure_id": d["measure_id"], "lag": MEASURES[d["measure_id"]]["lag"], "name": MEASURES[d["measure_id"]]["name"]} for d in decisions if MEASURES[d["measure_id"]]["lag"] >= 3]
    if long_projects:
        add("long_term_promises", .62 + min(.21, .07 * len(long_projects)), {"long_projects": long_projects, "latest_lag": long_projects[-1]["lag"], "horizon_quarters": HORIZON})
    positive_noncritical = [code for code, value in last["effects"].items() if value > 0 and all(code != item["indicator"] for item in critical)]
    if positive_noncritical and critical:
        add("cosmetic_vs_critical", .73, {"measure_id": last_id, "measure": last["name"], "improved_indicators": [{"code": code, "name": INDICATORS[code]["name"]} for code in positive_noncritical], "critical_metrics": critical[:8]})
    negatives = [{"code": code, "name": INDICATORS[code]["name"], "effect": value} for code, value in last["effects"].items() if value < 0]
    if negatives:
        add("negative_side_effect", .86, {"measure_id": last_id, "measure": last["name"], "negative_effects": negatives})
    for direction, count in direction_counts.items():
        if count >= 2:
            add("direction_obsession", .64 + .04 * (count - 2), {"direction": direction, "count": count, "total_decisions": len(decisions)})
    for synergy in SYNERGIES:
        linked = synergy["measures"]
        if last_id not in linked:
            continue
        if all(item in chosen for item in linked):
            add("active_synergy", .55, {"measures": linked, "bonus_indicator": synergy["indicator"], "bonus": synergy["bonus"], "decisions_used": len(linked)})
        else:
            missing = next(item for item in linked if item not in chosen)
            partner_available = any(item["measure_id"] == missing for item in feasible)
            add("unused_synergy", .57, {"chosen_measure": last_id, "possible_partner": missing, "partner_name": MEASURES[missing]["name"], "still_possible": remaining_decisions > 0 and partner_available})

    relevant_conflicts = _conflicts_touching(chosen)
    if relevant_conflicts:
        add("opportunity_cost", .61, {"blocked_alternatives": relevant_conflicts})

    if remaining_decisions and min_cost is not None and result["remaining"] < min_cost:
        add("budget_pressure", .88, {"remaining_budget": result["remaining"], "remaining_decisions": remaining_decisions, "minimum_feasible_cost": min_cost})
    elif remaining_decisions and result["remaining"] <= min_cost * remaining_decisions if min_cost is not None else False:
        add("budget_pressure", .66, {"remaining_budget": result["remaining"], "remaining_decisions": remaining_decisions, "minimum_feasible_cost": min_cost})

    if len(district_counts) >= 2 and len(district_counts) == sum(district_counts.values()) and len(district_counts) >= 2:
        add("scattered_strategy", .52 + .03 * len(district_counts), {"district_distribution": {DISTRICTS[key]["name"]: value for key, value in district_counts.items()}, "district_decisions": sum(district_counts.values())})
    if critical:
        add("unresolved_critical_problem", .82, {"critical_metrics": critical[:10], "critical_count": len(critical)})

    priority = {"scattered_strategy": 1, "direction_obsession": 1, "ignored_weak_district": 2, "unresolved_critical_problem": 2, "district_favoritism": 3, "negative_side_effect": 4, "budget_pressure": 5, "opportunity_cost": 6, "long_term_promises": 7, "megaproject": 8, "cosmetic_vs_critical": 9, "active_synergy": 11, "unused_synergy": 12}
    angles.sort(key=lambda angle: (priority.get(angle["type"], 99), -angle["severity"]))
    top_angles = angles[:3]
    return {
        "decision_number": len(decisions), "last_decision": {"measure_id": last_id, "measure": last["name"], "direction": last["direction"], "district": DISTRICTS[last_district]["name"] if last_district else None, "cost": last["cost"], "lag": last["lag"], "effects": last["effects"]},
        "history": [{"number": index + 1, "measure_id": item["measure_id"], "measure": MEASURES[item["measure_id"]]["name"], "direction": MEASURES[item["measure_id"]]["direction"], "district": DISTRICTS[item["district_id"]]["name"] if item["district_id"] else None, "cost": MEASURES[item["measure_id"]]["cost"], "lag": MEASURES[item["measure_id"]]["lag"]} for index, item in enumerate(decisions)],
        "spent_budget": spent, "remaining_budget": result["remaining"], "remaining_decisions": remaining_decisions,
        "district_decision_counts": {DISTRICTS[key]["name"]: value for key, value in district_counts.items()},
        "direction_counts": dict(direction_counts), "districts": {DISTRICTS[key]["name"]: {"score": round(value["score_after"], 2), "indicators": value["final"]} for key, value in result["districts"].items()},
        "critical_metrics": critical, "active_synergies": result["synergies"], "potential_synergies": [s for s in SYNERGIES if last_id in s["measures"]],
        "conflicts_avoided": relevant_conflicts, "feasible_alternatives": feasible[:20], "minimum_feasible_cost": min_cost,
        "media_angles": top_angles,
    }


def _conflicts_touching(chosen: set[str]) -> list[dict[str, Any]]:
    from .engine import CONFLICTS
    return [{"measures": c["measures"], "reason": c["reason"], "chosen_measure": next((item for item in c["measures"] if item in chosen), None), "alternative_measure": next((item for item in c["measures"] if item not in chosen), None)} for c in CONFLICTS if chosen.intersection(c["measures"])]


def deterministic_reaction(context: dict[str, Any]) -> dict[str, Any]:
    angles = context["media_angles"]
    angle = angles[0] if angles else {"type": "general_opportunity_cost", "facts": {}}
    kind, facts = angle["type"], angle["facts"]
    number = context["decision_number"]
    district_name = facts.get("ignored_weak_district") or facts.get("ignored_district")
    if not district_name and kind == "district_favoritism":
        district_name = facts.get("favored_district")
    if not district_name and kind == "cosmetic_vs_critical" and facts.get("critical_metrics"):
        district_name = facts["critical_metrics"][0]["district"]
    if not district_name and kind == "unresolved_critical_problem" and facts.get("critical_metrics"):
        district_name = facts["critical_metrics"][0]["district"]
    outlet = next((OUTLETS[key] for key, item in DISTRICTS.items() if item["name"] == district_name), OUTLETS["city"])
    if kind == "district_favoritism":
        ordinal = {2: "второй", 3: "третий", 4: "четвёртый", 5: "пятый"}.get(facts["measures_in_district"], f"ещё один ({facts['measures_in_district']}-й)")
        headline = f"{facts['favored_district']} получает {ordinal} проект. {facts.get('ignored_weak_district') or 'Городу'} снова предлагают подождать"
        metrics = facts.get("critical_metrics", [])
        sub = f"В {facts['favored_district']} направлены {facts['measures_in_district']} районных решения."
        if metrics:
            sub += " " + ", ".join(f"{m['indicator_name']} в {m['district']} — {m['value']}" for m in metrics[:2]) + "."
    elif kind == "ignored_weak_district":
        metrics = facts["critical_metrics"][:2]
        headline = f"{facts['ignored_district']} снова ждёт: критические показатели остались без адресного решения"
        sub = ", ".join(f"{m['indicator_name']} — {m['value']}" for m in metrics) + ". Районные вложения направлены в другие районы."
    elif kind == "megaproject":
        headline = f"{facts['budget_percent']}% бюджета — на один проект. Остальным решениям достанется меньше"
        sub = f"{facts['measure']} стоит {facts['cost']} из {BUDGET} единиц и рассчитан на {facts['lag']} квартала до полного эффекта."
    elif kind == "long_term_promises":
        headline = f"Город ждёт сейчас. В плане уже {len(facts['long_projects'])} проекта с длинным лагом"
        sub = f"У последнего решения лаг {facts['latest_lag']} квартала при горизонте симуляции {facts['horizon_quarters']} кварталов."
    elif kind == "negative_side_effect":
        effect = facts["negative_effects"][0]
        headline = f"Один показатель вверх — другой вниз: {effect['name']} получает {effect['effect']}"
        sub = f"У меры «{facts['measure']}» есть зафиксированный отрицательный эффект по этому показателю."
    elif kind == "direction_obsession":
        headline = f"{facts['count']} решения по направлению «{facts['direction']}». Остальным темам — очередь?"
        sub = f"Это {facts['count']} из {facts['total_decisions']} решений в текущем плане."
    elif kind == "budget_pressure":
        headline = f"Бюджетный коридор сужается: осталось {facts['remaining_budget']} единиц на {facts['remaining_decisions']} решения"
        sub = f"Самая дешёвая сейчас допустимая мера стоит {facts['minimum_feasible_cost']} единиц."
    elif kind == "unused_synergy":
        headline = f"У проекта есть связка — но второго участника пока нет"
        availability = "Связку ещё можно собрать." if facts["still_possible"] else "В текущем плане связку уже не собрать."
        sub = f"{facts['chosen_measure']} мог бы получить дополнительный эффект с {facts['possible_partner']} («{facts['partner_name']}»). {availability}"
    elif kind == "active_synergy":
        headline = "Две меры усиливают друг друга. И уже занимают два из пяти решений"
        sub = f"Связка {', '.join(facts['measures'])} даёт бонус {facts['bonus']} к показателю {facts['bonus_indicator']}."
    elif kind == "scattered_strategy":
        headline = "Всем понемногу — никому достаточно? Бюджет разошёлся по районам"
        sub = f"Районные решения распределены между {len(facts['district_distribution'])} районами."
    elif kind == "opportunity_cost":
        conflict = facts["blocked_alternatives"][0]
        blocked = conflict["alternative_measure"]
        headline = f"Выбрали {conflict['chosen_measure']}. {blocked} теперь вне плана"
        sub = f"Модель отмечает ограничение совместимости: {conflict['reason']}"
    elif kind == "unresolved_critical_problem":
        metric = facts["critical_metrics"][0]
        measure = context["last_decision"]["measure"]
        headline = f"«{measure}» принято. {metric['indicator_name']} в {metric['district']} всё ещё на {metric['value']}"
        sub = f"После решения №{number} в городе остаётся {facts['critical_count']} критических показателей ниже 40."
    else:
        last = context["last_decision"]
        headline = f"Решение №{number}: {last['measure']} — а остальные задачи подождут"
        sub = f"На меру направлено {last['cost']} бюджетных единиц; в плане использовано {number} из пяти решений."
    return {"outlet": outlet, "headline": headline[:100], "subheadline": sub, "angle": kind, "decision_number": number}
