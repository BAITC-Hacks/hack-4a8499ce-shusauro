from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from .engine import RuleViolation, calculate, public_dataset

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
    result: dict[str, Any]


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


@app.post("/explain")
def explain(request: ExplainRequest) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI-объяснение не настроено: добавьте OPENAI_API_KEY в backend/.env.")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        response = client.responses.create(
            model=model,
            instructions=(
                "Ты автор короткой хроники городского симулятора. Пиши по-русски живо и конкретно. "
                "Используй только предоставленные результаты детерминированной симуляции. "
                "Не пересчитывай числа, не выдумывай факты и причинные связи. Если данных недостаточно, "
                "описывай только переданные эффекты. Верни ровно 6 слайдов: по одному на каждую из пяти мер, "
                "затем общий итог. Каждый narrative — 35–60 слов, короткий заголовок."
            ),
            input=json.dumps(request.result, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "simulation_chronicle",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "slides": {
                                "type": "array",
                                "minItems": 6,
                                "maxItems": 6,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "narrative": {"type": "string"},
                                        "district": {"type": ["string", "null"]},
                                        "measure": {"type": ["string", "null"]},
                                        "observed_changes": {"type": "array", "items": {"type": "string"}},
                                        "tradeoff": {"type": ["string", "null"]},
                                    },
                                    "required": ["title", "narrative", "district", "measure", "observed_changes", "tradeoff"],
                                    "additionalProperties": False,
                                },
                            }
                        },
                        "required": ["slides"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        output = json.loads(response.output_text)
        if len(output.get("slides", [])) != 6:
            raise ValueError("Expected six slides")
        return output
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Не удалось получить AI-объяснение: {error}") from error
