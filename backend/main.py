from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .engine import DISTRICTS, INDICATORS, MEASURES, RuleViolation, calculate, public_dataset
from .media_analysis import OUTLETS, build_media_context, deterministic_reaction

load_dotenv(Path(__file__).with_name(".env"))


app = FastAPI(title="Qala city simulation API", version="0.1.0")
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class Decision(BaseModel):
    measure_id: str = Field(pattern=r"^M(?:[1-9]|1[0-4])$")
    district_id: str | None = None


class SimulationRequest(BaseModel):
    decisions: list[Decision]


class ExplainRequest(BaseModel):
    decisions: list[Decision]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/dataset")
def dataset() -> dict[str, Any]:
    return public_dataset()


@app.post("/simulate")
def simulate(request: SimulationRequest) -> dict[str, Any]:
    try:
        return calculate([decision.model_dump() for decision in request.decisions])
    except RuleViolation as error:
        raise HTTPException(status_code=422, detail=error.message) from error


@app.post("/preview")
def preview(request: SimulationRequest) -> dict[str, Any]:
    try:
        return calculate([decision.model_dump() for decision in request.decisions], require_five=False)
    except RuleViolation as error:
        raise HTTPException(status_code=422, detail=error.message) from error


def _openai_json(name: str, schema: dict[str, Any], instructions: str, facts: dict[str, Any]) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        instructions=instructions,
        input=json.dumps(facts, ensure_ascii=False),
        text={"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
    )
    return json.loads(response.output_text)


MEDIA_SCHEMA = {"type": "object", "properties": {
    "outlet": {"type": "string"}, "headline": {"type": "string"}, "subheadline": {"type": "string"},
    "angle": {"type": "string"}, "decision_number": {"type": "integer"},
}, "required": ["outlet", "headline", "subheadline", "angle", "decision_number"], "additionalProperties": False}

FINAL_SCHEMA = {"type": "object", "properties": {
    "headline": {"type": "string"}, "summary": {"type": "string"}, "strategy_read": {"type": "string"},
    "strengths": {"type": "array", "items": {"type": "string"}},
    "risks": {"type": "array", "items": {"type": "string"}},
    "district_outlook": {"type": "array", "items": {"type": "object", "properties": {
        "district": {"type": "string"}, "note": {"type": "string"}, "score_delta": {"type": "number"},
    }, "required": ["district", "note", "score_delta"], "additionalProperties": False}},
}, "required": ["headline", "summary", "strategy_read", "strengths", "risks", "district_outlook"], "additionalProperties": False}

@app.post("/media-reaction")
def media_reaction(request: ExplainRequest) -> dict[str, Any]:
    decisions = [decision.model_dump() for decision in request.decisions]
    try:
        context = build_media_context(decisions)
        fallback = deterministic_reaction(context)
        allowed_angles = {item["type"] for item in context["media_angles"]}
        instructions = (
            "Ты — главный редактор вымышленной язвительной городской газеты симулятора. Напиши короткую негативную первую полосу. "
            "Пиши по-русски, остро и умно, без оскорблений личности. Даже хорошая мера имеет цену, лаг, opportunity cost либо нерешённые задачи. "
            "Используй ТОЛЬКО переданные backend facts и TOP media angles. Не пересчитывай показатели и бюджет, не придумывай последствия, протесты, смерти, коррупцию, аварии, опросы, цитаты, рейтинги или общественную реакцию. "
            "Выбери один из top angles. Угол должен соответствовать его фактам. Заголовок до 100 символов, подзаголовок — 1–2 коротких предложения. "
            f"outlet выбери только из списка: {', '.join(OUTLETS.values())}. angle выбери из: {', '.join(allowed_angles)}. Факты точны, интерпретация может быть несправедливой."
        )
        generated = _openai_json("media_reaction", MEDIA_SCHEMA, instructions, context)
        if generated:
            if generated["angle"] not in allowed_angles or generated["outlet"] not in OUTLETS.values() or generated["decision_number"] != context["decision_number"]:
                return fallback
            positive_phrases = ("отличное решение", "отличная работа", "всё правильно", "победа акима", "идеальный план", "успешно решил")
            if any(phrase in (generated["headline"] + " " + generated["subheadline"]).lower() for phrase in positive_phrases):
                return fallback
            generated["headline"] = generated["headline"][:100]
            return generated
        return fallback
    except Exception:
        return deterministic_reaction(build_media_context(decisions))


@app.post("/final-analysis")
def final_analysis(request: ExplainRequest) -> dict[str, Any]:
    decisions = [decision.model_dump() for decision in request.decisions]
    try:
        result = calculate(decisions, require_five=True)
    except RuleViolation as error:
        raise HTTPException(status_code=422, detail=error.message) from error
    facts = {"result": result, "measures": MEASURES, "districts": DISTRICTS, "indicators": INDICATORS}
    instructions = (
        "Ты — итоговый аналитик симулятора городского управления. Подготовь один цельный аналитический экран на русском языке. "
        "Источник истины — переданные готовые результаты deterministic backend. Не пересчитывай Score, эффекты, lag, бюджет; не придумывай причинные связи или факты. "
        "Объясни итоговый курс, заметные результаты и компромиссы. Сильные стороны должны подтверждаться положительными изменениями; риски — оставшимися критическими метриками, отрицательными эффектами, бюджетом/лагом или концентрацией плана. "
        "Не превращай анализ в шесть слайдов. Коротко: заголовок, summary 2–4 предложения, strategy_read, до 3 strengths и risks, по одной краткой factual note на район."
    )
    try:
        generated = _openai_json("final_analysis", FINAL_SCHEMA, instructions, facts)
    except Exception:
        generated = None
    if generated:
        by_name = {district["name"]: district for district in result["districts"].values()}
        names = [item["district"] for item in generated["district_outlook"]]
        if len(names) == len(by_name) and set(names) == set(by_name):
            for item in generated["district_outlook"]:
                item["score_delta"] = by_name[item["district"]]["score_delta"]
            return generated
    critical = [{"district": district["name"], "indicator": code, "name": INDICATORS[code]["name"], "value": value}
                for district in result["districts"].values() for code, value in district["final"].items() if value < 40]
    return {
        "headline": f"Городской курс: {result['final_score']:.2f} балла",
        "summary": f"Пять решений использовали {result['spent']} из {result['budget']} бюджетных единиц. Итоговый QoL Score — {result['final_score']:.2f} ({result['score_delta']:+.2f} к исходному). Этот экран объединяет расчёт симулятора и его проверяемые последствия.",
        "strategy_read": f"План распределил решения по {len(result['direction_counts'])} направлениям; активных синергий: {len(result['synergies'])}. Самый слабый район по итоговому показателю — {DISTRICTS[result['weakest_district_after']]['name']}.",
        "strengths": [f"Положительный суммарный сдвиг показателей: {result['score_delta']:+.2f} QoL Score." if result["score_delta"] >= 0 else "Пять мер выбраны в пределах бюджета и правил симулятора.", f"Активировано синергий: {len(result['synergies'])}."][:2],
        "risks": ([f"После плана остаются критические показатели ниже 40: {len(critical)}."] if critical else []) + ([f"Неизрасходованный бюджет: {result['remaining']} ед."] if result["remaining"] else []),
        "district_outlook": [{"district": data["name"], "note": f"QoL {data['score_before']:.2f} → {data['score_after']:.2f}; изменение {data['score_delta']:+.2f}." + (f" Критические показатели: {', '.join(data['critical_indicators'])}." if data["critical_indicators"] else " Критических показателей ниже 40 нет."), "score_delta": data["score_delta"]} for data in result["districts"].values()],
    }
