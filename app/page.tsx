"use client";

import { useEffect, useMemo, useState } from "react";

const API = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");
const DISTRICT_ORDER = ["esil", "almaty", "saryarka", "baykonur", "nura"];
const INDICATOR_ORDER = ["T1", "T2", "E1", "E2", "S1", "S2", "B1", "B2", "C1", "C2"];
type District = { name: string; population: number; profile: string; indicators: Record<string, number> };
type Measure = { name: string; direction: string; type: "Город" | "Район"; cost: number; lag: number; effects: Record<string, number>; description: string };
type Decision = { measure_id: string; district_id: string | null };
type Dataset = { budget: number; baseline_score: number; horizon_quarters: number; districts: Record<string, District>; indicators: Record<string, { name: string; direction: string; weight: number }>; measures: Record<string, Measure>; synergies: { measures: string[]; indicator: string; bonus: number; district_measure: string; description: string }[]; conflicts: { measures: string[]; same_district: boolean; reason: string }[] };
type Simulation = { spent: number; remaining: number; decisions_count: number; simulation_complete: boolean; baseline_score: number; final_score: number; score_delta: number; city_score_before: number; city_score_after: number; weakest_district_before: string; weakest_district_after: string; critical_count_before: number; critical_count_after: number; districts: Record<string, { name: string; population: number; profile: string; score_before: number; score_after: number; score_delta: number; initial: Record<string, number>; final: Record<string, number>; critical_indicators: string[] }>; indicators: Dataset["indicators"]; measures: (Measure & { measure_id: string; district_id: string | null; affected_districts: string[]; realized_factor: number })[]; synergies: { measures: string[]; indicator: string; bonus: number; district_id: string; description: string }[]; direction_counts: Record<string, number> };
type MediaReaction = { outlet: string; headline: string; subheadline: string; angle: string; decision_number: number };
type FinalAnalysis = { headline: string; summary: string; strategy_read: string; strengths: string[]; risks: string[]; district_outlook: { district: string; note: string; score_delta: number }[] };
type Synergy = Dataset["synergies"][number];

const fmt = (value: number, digits = 1) => Number(value).toFixed(digits);
const sign = (value: number) => value > 0 ? `+${fmt(value)}` : fmt(value);

async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...options, headers: { "Content-Type": "application/json", ...options?.headers } });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Ошибка сервера (${response.status})`);
  return payload as T;
}

function scoreTone(score: number) {
  if (score < 52) return "#d77b6b";
  if (score < 59) return "#d6b65e";
  return "#8cbd79";
}

export default function Home() {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [simulation, setSimulation] = useState<Simulation | null>(null);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [mode, setMode] = useState<"city" | "district">("city");
  const [activeDistrict, setActiveDistrict] = useState<string | null>(null);
  const [inspectedDistrict, setInspectedDistrict] = useState<string | null>("nura");
  const [measureId, setMeasureId] = useState<string | null>(null);
  const [filter, setFilter] = useState("Все");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mediaReaction, setMediaReaction] = useState<MediaReaction | null>(null);
  const [finalResult, setFinalResult] = useState<Simulation | null>(null);
  const [finalAnalysis, setFinalAnalysis] = useState<FinalAnalysis | null>(null);
  const [finalizing, setFinalizing] = useState(false);

  useEffect(() => {
    api<Dataset>("/dataset").then(setDataset).catch((e) => setError(`Не удалось подключиться к симулятору: ${e.message}. Запустите backend по инструкции в README.`));
  }, []);

  const selectedMeasure = measureId && dataset ? dataset.measures[measureId] : null;
  const spent = decisions.reduce((total, item) => total + (dataset?.measures[item.measure_id]?.cost || 0), 0);
  const remaining = (dataset?.budget || 100) - spent;
  const directions = useMemo(() => ["Все", ...Array.from(new Set(Object.values(dataset?.measures || {}).map((m) => m.direction)))], [dataset]);
  const visibleIds = useMemo(() => {
    if (!dataset) return [];
    return Object.entries(dataset.measures).filter(([, m]) => mode === "city" ? m.type === "Город" : m.type === "Район" && !!activeDistrict).filter(([, m]) => filter === "Все" || m.direction === filter).map(([id]) => id);
  }, [dataset, mode, activeDistrict, filter]);

  const isActiveSynergy = (id: string) => !!dataset?.synergies.some((s) => s.measures.includes(id) && s.measures.every((linked) => decisions.some((d) => d.measure_id === linked)));
  const hasPotentialSynergy = (id: string) => !!dataset?.synergies.some((s) => s.measures.includes(id));
  const hasPotentialConflict = (id: string) => !!dataset?.conflicts.some((c) => c.measures.includes(id));
  const conflictWith = (id: string, districtId: string | null) => {
    if (!dataset) return null;
    for (const picked of decisions) {
      const rule = dataset.conflicts.find((c) => c.measures.includes(id) && c.measures.includes(picked.measure_id));
      if (rule && (!rule.same_district || (districtId && districtId === picked.district_id))) return { picked, reason: rule.reason };
    }
    return null;
  };
  const statusOf = (id: string, districtId = activeDistrict) => {
    if (!dataset) return "available";
    if (decisions.some((d) => d.measure_id === id)) return "applied";
    if (conflictWith(id, districtId)) return "conflict";
    if (dataset.measures[id].cost > remaining) return "unaffordable";
    if ((simulation?.direction_counts?.[dataset.measures[id].direction] || 0) >= 2) return "unavailable";
    return isActiveSynergy(id) ? "active" : "available";
  };

  async function applyMeasure(id: string) {
    if (!dataset || busy || decisions.length >= 5) return;
    const m = dataset.measures[id];
    if (m.type === "Район" && !activeDistrict) { setError("Сначала выберите район на карте."); setMode("district"); return; }
    const next = [...decisions, { measure_id: id, district_id: m.type === "Район" ? activeDistrict : null }];
    setBusy(true); setError("");
    try {
      const result = await api<Simulation>("/preview", { method: "POST", body: JSON.stringify({ decisions: next }) });
      setDecisions(next);
      setSimulation(result);
      setMeasureId(null);
      setMediaReaction({ outlet: "СТОЛИЧНЫЙ ШУМ", headline: "Редакция уже верстает выпуск…", subheadline: "Проверяем факты принятого решения и всей истории плана.", angle: "loading", decision_number: next.length });
      try {
        const reaction = await api<MediaReaction>("/media-reaction", { method: "POST", body: JSON.stringify({ decisions: next }) });
        setMediaReaction(reaction);
      } catch {
        setMediaReaction({ outlet: "СТОЛИЧНЫЙ ШУМ", headline: `Решение №${next.length}: на что не хватит этих ресурсов?`, subheadline: `В план внесено «${m.name}» стоимостью ${m.cost} ед.; использовано ${next.length} из пяти решений.`, angle: "opportunity_cost", decision_number: next.length });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось обработать принятое решение.");
    } finally { setBusy(false); }
  }

  async function continueAfterMedia() {
    if (!mediaReaction || mediaReaction.angle === "loading" || finalizing) return;
    const isLast = decisions.length === 5;
    setMediaReaction(null);
    if (!isLast) return;
    setFinalizing(true); setError("");
    try {
      const payload = { decisions };
      const result = await api<Simulation>("/simulate", { method: "POST", body: JSON.stringify(payload) });
      setSimulation(result);
      setFinalResult(result);
      const analysis = await api<FinalAnalysis>("/final-analysis", { method: "POST", body: JSON.stringify(payload) });
      setFinalAnalysis(analysis);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось завершить анализ результатов.");
      setMediaReaction({ outlet: "СТОЛИЧНЫЙ ШУМ", headline: "Итоговый выпуск задерживается", subheadline: "Ваши пять решений сохранены. Нажмите «Продолжить», чтобы повторить итоговый расчёт.", angle: "retry", decision_number: 5 });
    } finally { setFinalizing(false); }
  }

  function selectMode(next: "city" | "district") {
    setMode(next); setFilter("Все"); setError("");
    if (next === "district") { setActiveDistrict(null); setInspectedDistrict(null); }
  }

  if (!dataset) return <main className="loading-screen"><div className="brand-mark"><i></i><i></i><i></i></div><p>{error || "Подключаем городской штаб…"}</p><small>BACKEND · API</small></main>;

  const inspect = (id: string) => {
    setInspectedDistrict(id);
    if (mode === "district" && decisions.length < 5) { setActiveDistrict(id); setFilter("Все"); setError(""); }
  };
  const districtCurrent = (id: string) => simulation?.districts[id]?.final || dataset.districts[id].indicators;
  const districtScore = (id: string) => simulation?.districts[id]?.score_after ?? Object.entries(dataset.districts[id].indicators).reduce((score, [code, value]) => score + value * dataset.indicators[code].weight, 0);
  const regionName = (id: string | null | undefined) => id && dataset.districts[id] ? dataset.districts[id].name : "Весь город";

  if (mediaReaction) return (
    <main className="app-shell media-shell">
      <section className="newspaper" aria-live="polite">
        <header className="paper-masthead"><span>QALA · ГОРОДСКАЯ ХРОНИКА</span><span>ВНЕОЧЕРЕДНОЙ ВЫПУСК № {String(mediaReaction.decision_number).padStart(2, "0")}</span></header>
        <div className="paper-rule" />
        <div className="paper-edition">{mediaReaction.outlet}</div>
        <div className="paper-kicker">РЕШЕНИЕ АКИМА № {mediaReaction.decision_number} · {mediaReaction.angle === "loading" ? "ПРОВЕРКА ФАКТОВ" : "РЕДАКЦИОННЫЙ РАЗБОР"}</div>
        <h1 className="paper-headline">{mediaReaction.headline}</h1>
        <p className="paper-subheadline">{mediaReaction.subheadline}</p>
        <div className="paper-footer"><span>ФАКТЫ — ИЗ ГОРОДСКОЙ МОДЕЛИ · ТОН — РЕДАКЦИОННЫЙ</span><span>{mediaReaction.decision_number} / 5 РЕШЕНИЙ</span></div>
        <button className="paper-continue" disabled={mediaReaction.angle === "loading" || finalizing} onClick={continueAfterMedia}>{mediaReaction.angle === "retry" ? "Повторить итоговый расчёт" : mediaReaction.decision_number === 5 ? "Продолжить к итогам" : "Продолжить"} <span>→</span></button>
      </section>
    </main>
  );

  if (finalizing) return <main className="loading-screen"><div className="brand-mark"><i></i><i></i><i></i></div><p>Симулятор рассчитывает итог, аналитик готовит сводку…</p><small>DETERMINISTIC RESULT · FINAL ANALYST</small></main>;

  if (finalResult && finalAnalysis) return (
    <main className="app-shell result-shell">
      <header className="topbar"><a className="brand" href="#"><span className="brand-mark"><i></i><i></i><i></i></span><span><b>QALA</b><small>ИТОГОВЫЙ АНАЛИЗ</small></span></a><div className="top-context">СИМУЛЯЦИЯ ЗАВЕРШЕНА</div><button className="reset-button" onClick={() => { setDecisions([]); setSimulation(null); setFinalResult(null); setFinalAnalysis(null); setMediaReaction(null); setMode("city"); setActiveDistrict(null); setInspectedDistrict("nura"); setError(""); }}>Новый сценарий ↻</button></header>
      <section className="result-hero"><div><div className="eyebrow">ASTANA QUALITY OF LIFE SCORE · ИТОГ</div><h1>{finalAnalysis.headline}</h1><p>{finalAnalysis.summary}</p></div><div className="score-card"><span>ИТОГОВЫЙ QOL SCORE</span><strong>{fmt(finalResult.final_score, 2)}</strong><div className={`score-change ${finalResult.score_delta >= 0 ? "positive" : "negative"}`}>{sign(finalResult.score_delta)} к исходным {fmt(finalResult.baseline_score, 2)}</div><div className="score-scale"><i style={{ width: `${Math.max(0, Math.min(100, finalResult.final_score))}%` }} /></div><small>Расчёт детерминированной модели</small></div></section>
      <section className="result-grid">
        <section className="panel result-panel"><div className="eyebrow">АНАЛИЗ КУРСА</div><h2>Что говорят результаты</h2><p className="final-strategy">{finalAnalysis.strategy_read}</p><div className="final-columns"><div><h3>Что сработало</h3>{finalAnalysis.strengths.map((item, i) => <p className="final-note strength" key={i}>{item}</p>)}</div><div><h3>Что осталось под давлением</h3>{(finalAnalysis.risks.length ? finalAnalysis.risks : ["Критических показателей ниже 40 после расчёта не осталось."]).map((item, i) => <p className="final-note risk" key={i}>{item}</p>)}</div></div></section>
        <section className="panel result-panel"><div className="eyebrow">ПО РАЙОНАМ</div><h2>Изменение QoL</h2><div className="result-districts">{DISTRICT_ORDER.map((id) => { const d = finalResult.districts[id]; return <div className="result-district" key={id}><span className="result-district-name">{d.name}</span><div className="result-bar"><i style={{ width: `${d.score_after}%`, background: scoreTone(d.score_after) }} /></div><span className="result-score">{fmt(d.score_after, 2)}</span><small className="district-delta">Было {fmt(d.score_before, 2)} · {sign(d.score_delta)}</small></div>; })}</div></section>
        <section className="panel result-panel full-width"><div className="eyebrow">РАЙОННЫЙ АНАЛИЗ</div><h2>Пять разных последствий</h2><div className="district-analysis">{finalAnalysis.district_outlook.map((item) => <article key={item.district}><div><b>{item.district}</b><strong className={item.score_delta >= 0 ? "delta-positive" : "delta-negative"}>{sign(item.score_delta)}</strong></div><p>{item.note}</p></article>)}</div></section>
        <section className="panel result-panel full-width"><div className="eyebrow">ПРИНЯТЫЕ РЕШЕНИЯ · {finalResult.spent}/{dataset.budget} ЕД.</div><h2>План акима</h2><div className="result-measures">{finalResult.measures.map((m, index) => <div className="result-measure" key={m.measure_id}><span className="result-no">0{index + 1}</span><span><b>{m.name}</b><small>{m.measure_id} · {m.district_id ? regionName(m.district_id) : "город"} · эффект реализован на {fmt(m.realized_factor * 100, 0)}%</small></span><strong>{m.cost} ед.</strong></div>)}</div>{finalResult.synergies.length > 0 && <div className="active-synergies"><b>Активные синергии</b>{finalResult.synergies.map((item) => <span key={item.measures.join("-")}>{item.measures.join(" + ")} · {regionName(item.district_id)} · {item.indicator} +{item.bonus}</span>)}</div>}</section>
      </section><footer className="footer-note"><span>DETERMINISTIC MODEL + FINAL AI ANALYST</span><span>СИНТЕТИЧЕСКИЕ ДАННЫЕ · НЕ ПРОГНОЗ</span><span>BUILD 0.2</span></footer>
    </main>
  );

  const districtInfo = inspectedDistrict ? dataset.districts[inspectedDistrict] : null;
  const inspectedValues = inspectedDistrict ? districtCurrent(inspectedDistrict) : null;
  const qScore = simulation?.final_score ?? dataset.baseline_score;
  const sortRank: Record<string, number> = { active: 0, available: 1, unavailable: 2, unaffordable: 3, conflict: 4, applied: 5 };
  const orderedIds = [...visibleIds].sort((a, b) => sortRank[statusOf(a)] - sortRank[statusOf(b)] || Number(a.slice(1)) - Number(b.slice(1)));
  const relatedSynergies = selectedMeasure && dataset.synergies.filter((s) => s.measures.includes(measureId!)) || [];
  const relatedConflicts = selectedMeasure && dataset.conflicts.filter((c) => c.measures.includes(measureId!)) || [];

  return <main className="app-shell">
    <header className="topbar"><a className="brand" href="#"><span className="brand-mark"><i></i><i></i><i></i></span><span><b>QALA</b><small>АКИМ НА 5 ЧАСОВ</small></span></a><div className="top-context"><span className="live-dot"></span> КРИЗИСНЫЙ ШТАБ <span className="context-divider">/</span> АСТАНА</div><div className="top-meta">СЦЕНАРИЙ 01<span className="top-separator"></span>СИМУЛЯЦИЯ · H={dataset.horizon_quarters}</div></header>
    <section className="intro-strip"><div><div className="eyebrow">ВАШ ГОРОД. ВАШИ РЕШЕНИЯ.</div><h1>Пять решений.<br/><em>Один город.</em></h1><p>Распределите общий бюджет между городскими инициативами. У каждого решения есть цена, срок и последствия для качества жизни в районах.</p></div><div className="intro-stats"><div><span>БЮДЖЕТ</span><strong>{dataset.budget} <small>ед.</small></strong></div><div><span>РЕШЕНИЯ</span><strong>{String(decisions.length).padStart(2,"0")} <small>/ 05</small></strong></div><div><span>ГОРОДСКОЙ QOL</span><strong>{fmt(qScore,2)} <small>{simulation ? "текущий" : "исходный"}</small></strong></div></div></section>
    <section className="command-bar"><div className="command-title"><span className="command-index">01</span><span>ГОРОДСКОЙ ПЛАН</span></div><div className="decision-progress" aria-label={`Принято решений ${decisions.length} из 5`}>{[0,1,2,3,4].map((i) => <i className={`progress-dot ${i < decisions.length ? "filled" : ""}`} key={i}></i>)}</div><div className="budget-meter"><div className="budget-label"><span>ОСТАТОК БЮДЖЕТА</span><strong>{remaining} <small>ед.</small></strong></div><div className="meter-track"><i style={{ width: `${remaining}%` }}></i></div></div></section>
    <section className="workspace">
      <div className="left-column">
        <section className="panel map-panel"><div className="panel-heading"><div><div className="eyebrow">ИНТЕРАКТИВНАЯ КАРТА</div><h2>{mode === "district" ? activeDistrict ? `Район: ${regionName(activeDistrict)}` : "Выберите район" : "Районы города"}</h2></div><span className="map-caption">{mode === "district" ? <><i></i>режим районных мер</> : "схематическая карта · Астана"}</span></div>
          <div className="map-layout"><div className={`map-art ${mode === "district" && !activeDistrict ? "selecting-region" : ""}`}><div className="map-grid"></div><svg className="city-map" viewBox="0 0 440 510" role="img" aria-label="Схематическая карта районов Астаны">
            <path className="river" d="M28 270 C92 245 132 287 184 266 S270 242 321 263 S384 288 425 258"/><path className="road" d="M83 81 135 111 206 102 263 125 338 111 386 143"/><path className="road road-two" d="M49 354 109 325 172 337 237 316 306 345 377 322"/>
            {Object.entries({ baykonur:"M151 35 238 25 314 53 347 100 321 148 268 163 219 139 167 157 124 117Z", saryarka:"M48 127 124 117 167 157 188 220 155 281 111 293 55 267 33 213Z", nura:"M33 213 55 267 111 293 134 354 114 420 62 433 25 391 20 310Z", esil:"M167 157 219 139 268 163 291 222 271 284 237 334 188 357 134 354 155 281 188 220Z", almaty:"M268 163 321 148 378 177 416 225 398 284 377 322 306 345 271 284 291 222Z" }).map(([id, d]) => <path key={id} className={`district district-${id} ${inspectedDistrict === id ? "active" : ""}`} d={d} fill={scoreTone(districtScore(id))} onClick={() => inspect(id)} onMouseEnter={() => setInspectedDistrict(id)} />)}
            {Object.entries({ baykonur:[234,83,"БАЙКОНУР"], saryarka:[99,204,"САРЫАРКА"], nura:[70,351,"НУРА"], esil:[211,255,"ЕСИЛЬ"], almaty:[344,247,"АЛМАТЫ"] }).map(([id, values]) => { const [x,y,label]=values as [number,number,string]; return <g key={id} className="district-label" onClick={() => inspect(id)} onMouseEnter={() => setInspectedDistrict(id)}><text x={x} y={y}>{label}</text><text className="district-score" x={x} y={y+22}>{fmt(districtScore(id),1)}</text></g>; })}
            </svg><div className="map-north">N <span>↑</span></div><div className="map-scale"><i></i><span>СХЕМАТИЧНО</span></div></div>
            <aside className="district-info"><div className="district-info-top"><span className="info-kicker">{mode === "district" && activeDistrict === inspectedDistrict ? "РАЙОН ДЛЯ РЕШЕНИЯ" : "ОБЗОР РАЙОНА"}</span><span className="info-chip">{districtInfo ? `${Math.round(districtInfo.population*100)}% жителей` : "—"}</span></div><h3>{districtInfo?.name || "Нажмите на район"}</h3><p>{districtInfo?.profile || "Выберите район на карте, чтобы посмотреть профиль и показатели."}</p>{districtInfo && inspectedValues && <><div className="district-score-line"><span>ОЦЕНКА QOL</span><b style={{color:scoreTone(districtScore(inspectedDistrict!))}}>{fmt(districtScore(inspectedDistrict!),2)}</b></div><div className="stat-list">{INDICATOR_ORDER.map((code) => <div className="stat-row" key={code}><span className="stat-code">{code}</span><span className="stat-name">{dataset.indicators[code].name}</span><span className="stat-value">{fmt(inspectedValues[code],0)}</span></div>)}</div></>}</aside></div>
          <div className="map-legend"><span><i className="legend-dot legend-good"></i> выше средних</span><span><i className="legend-dot legend-mid"></i> близко к средним</span><span><i className="legend-dot legend-low"></i> требует внимания</span><small>Районный QOL · пересчитывается после решения</small></div>
          <div className="measure-mode"><button className={mode === "city" ? "active" : ""} onClick={() => selectMode("city")}>Городские меры <small>5</small></button><button className={mode === "district" ? "active" : ""} onClick={() => selectMode("district")}>Районные меры <small>9</small></button><span>{mode === "district" ? activeDistrict ? `Выбран: ${regionName(activeDistrict)}` : "Выберите район на карте, затем меру" : "Меры влияют на все 5 районов"}</span></div>
        </section>

        <section className="panel measures-panel" id="measures"><div className="panel-heading measures-heading"><div><div className="eyebrow">КАТАЛОГ ИНИЦИАТИВ</div><h2>{mode === "city" ? "Городские меры" : activeDistrict ? `Меры района «${regionName(activeDistrict)}»` : "Сначала выберите район"}</h2></div><span className="heading-note">Решение нельзя отменить</span></div>
          {mode === "district" && !activeDistrict ? <div className="district-prompt"><span>↖</span><div><b>Выберите район на карте</b><p>После выбора здесь появятся районные инициативы, их конфликты и доступность для этого района.</p></div></div> : <><div className="filter-row">{directions.map((item) => <button className={`filter-chip ${filter === item ? "active" : ""}`} key={item} onClick={() => setFilter(item)}>{item}</button>)}</div><div className="measure-list">{orderedIds.map((id) => { const m=dataset.measures[id]; const state=statusOf(id); const conflict=conflictWith(id,mode === "district" ? activeDistrict : null); const active=decisions.find((d)=>d.measure_id===id); const alreadyApplied=!!active; const potential=hasPotentialSynergy(id); const limited=hasPotentialConflict(id); const activeBuff=isActiveSynergy(id); return <article key={id} className={`measure-card ${state === "applied" ? "selected" : ""} ${state === "conflict" ? "blocked" : ""} ${activeBuff ? "buff-active" : ""}`} onClick={() => setMeasureId(id)}><span className="measure-index">{id}</span><div className="measure-main"><div className="measure-title-row"><span className="measure-title">{m.name}</span><span className="measure-code">{m.direction}</span>{activeBuff && <span className="synergy-tag">✳ АКТИВНАЯ СИНЕРГИЯ</span>}</div><p className="measure-description">{m.description}</p><div className="measure-meta"><span className="measure-cost">{m.cost} ед.</span><span>⏱ {m.lag} кв.</span>{potential && <span title="У этой меры есть синергия с другой мерой" className="relation-indicator synergy-indicator">+ СИНЕРГИЯ</span>}{limited && <span title="У этой меры есть ограничения совместимости с другими решениями" className="relation-indicator restriction-indicator">− ОГРАНИЧЕНИЕ</span>}</div></div><div className="measure-right"><span className="measure-kind">{m.type.toUpperCase()}</span><button className="select-measure" aria-label="Открыть подробности" title="Открыть подробности" onClick={(e) => {e.stopPropagation(); setMeasureId(id);}}>›</button></div>{conflict && <div className="blocked-note">НЕСОВМЕСТИМО С {conflict.picked.measure_id} · {conflict.reason}</div>}{state === "unavailable" && <div className="blocked-note neutral-note">ЛИМИТ: уже выбрано 2 меры направления «{m.direction}»</div>}{state === "unaffordable" && <div className="blocked-note neutral-note">НЕ ХВАТАЕТ БЮДЖЕТА · осталось {remaining} ед.</div>}{alreadyApplied && <div className="blocked-note applied-note">ПРИНЯТО ОКОНЧАТЕЛЬНО · {regionName(active?.district_id)}</div>}</article>; })}{orderedIds.length === 0 && <div className="district-prompt"><b>Нет мер по этому фильтру</b><p>Выберите другое направление.</p></div>}</div></>}
        </section>
      </div>

      <aside className="right-column"><section className="panel plan-panel"><div className="panel-heading"><div><div className="eyebrow">ВАШ СЦЕНАРИЙ</div><h2>План решений</h2></div><span className="plan-count">{String(decisions.length).padStart(2,"0")}<span> / 05</span></span></div><div className="plan-list">{decisions.map((d,index)=>{const m=dataset.measures[d.measure_id];return <div className="plan-item" key={`${d.measure_id}-${d.district_id}`}><span className="plan-number">0{index+1}</span><div><div className="plan-item-title">{m.name}</div><div className="plan-item-sub">{d.measure_id} · {regionName(d.district_id)} · {m.cost} ед.</div>{simulation && <div className="plan-reveal">{Object.entries(m.effects).map(([code,value])=><span key={code}>{code} {sign(value*((8-m.lag)/8))} · </span>)}с учётом срока</div>}</div><span className="applied-check">✓</span></div>})}{Array.from({length:5-decisions.length},(_,i)=><div className="plan-empty" key={i}><span>{String(decisions.length+i+1).padStart(2,"0")}</span><i>решение ожидает</i></div>)}</div><div className="plan-footer"><div className="plan-total"><span>ИТОГО В ПЛАНЕ</span><strong>{spent} <small>/ {dataset.budget} ед.</small></strong></div><p className="button-hint">После каждого решения выйдет газетная реакция. После пятой нажмите «Продолжить к итогам». Решения отменить нельзя.</p></div></section>
        <section className="panel revealed-panel"><div className="eyebrow">КАК УСТРОЕН РАСЧЁТ</div><h2>Городские показатели</h2><p className="revealed-lead">Эффекты и синергии открыты в карточке каждой меры. На карте видно исходное состояние и изменения после принятых решений.</p>{simulation?.synergies?.length ? <div className="active-synergies"><b>АКТИВНЫЕ СИНЕРГИИ</b>{simulation.synergies.map(s=><span key={s.measures.join("-")}>✳ {s.measures.join(" + ")} · {regionName(s.district_id)} · {s.indicator} +{s.bonus}</span>)}</div> : <div className="reveal-empty"><span>✳</span><p>Синергии указаны в карточках и активируются, когда в план попадают обе связанные меры.</p></div>}<div className="synergy-note"><span>ⓘ</span><p>Полный эффект уменьшается с учётом лага и горизонта в {dataset.horizon_quarters} кварталов.</p></div></section></aside>
    </section>
    {error && <div className="toast-error" role="alert">{error}<button onClick={()=>setError("")}>×</button></div>}
    {busy && <div className="busy-overlay"><span className="spinner"></span><b>Проверяем решение и пересчитываем показатели…</b></div>}
    {selectedMeasure && measureId && <div className="modal-backdrop" onClick={()=>setMeasureId(null)}><section role="dialog" aria-modal="true" className="measure-modal" onClick={(e)=>e.stopPropagation()}><button className="dialog-close" onClick={()=>setMeasureId(null)} aria-label="Закрыть">×</button><div className="eyebrow">{measureId} · {selectedMeasure.direction.toUpperCase()}</div><h2>{selectedMeasure.name}</h2><p className="modal-description">{selectedMeasure.description}</p><div className="modal-meta"><div><span>СТОИМОСТЬ</span><b>{selectedMeasure.cost} ед.</b></div><div><span>ТИП</span><b>{selectedMeasure.type}</b></div><div><span>ЛАГ</span><b>{selectedMeasure.lag} кв.</b></div>{selectedMeasure.type === "Район"&&<div><span>РАЙОН</span><b>{regionName(activeDistrict)}</b></div>}</div><div className="modal-section"><h3>ЭФФЕКТЫ</h3><p className="modal-hint">Полный эффект по окончании горизонта. В итоговый расчёт войдёт доля с учётом лага.</p><div className="modal-effects">{Object.entries(selectedMeasure.effects).map(([code,value])=><div key={code}><b>{code}</b><span>{dataset.indicators[code].name}</span><strong className={value<0?"delta-negative":"delta-positive"}>{sign(value)}</strong></div>)}</div><p className="realized-hint">На горизонте {dataset.horizon_quarters} кварталов реализуется {fmt((dataset.horizon_quarters-selectedMeasure.lag)/dataset.horizon_quarters*100,0)}% эффекта.</p></div><div className="modal-section"><h3>СИНЕРГИИ {relatedSynergies.length===0&&<small>нет</small>}</h3>{relatedSynergies.map((s:Synergy)=><p className={`relation-row ${s.measures.every((id)=>decisions.some((d)=>d.measure_id===id))?"relation-active":""}`} key={s.measures.join("-")}><span>✳</span>{s.description} <b>{s.indicator} +{s.bonus} · {s.measures.map((id)=>dataset.measures[id].name).join(" + ")}</b>{s.measures.every((id)=>decisions.some((d)=>d.measure_id===id))&&<em>✓ АКТИВНА</em>}</p>)}</div><div className="modal-section"><h3>КОНФЛИКТЫ {relatedConflicts.length===0&&<small>нет</small>}</h3>{relatedConflicts.map((c)=><p className="relation-row conflict-row" key={c.measures.join("-")}><span>×</span>{c.reason}<b> {c.measures.join(" + ")}</b></p>)}</div><div className="modal-actions"><button className="quiet-button" onClick={()=>setMeasureId(null)}>Отложить</button><button className="apply-button" disabled={busy||decisions.length>=5||statusOf(measureId)==="conflict"||statusOf(measureId)==="unavailable"||statusOf(measureId)==="unaffordable"||decisions.some((d)=>d.measure_id===measureId)} onClick={()=>applyMeasure(measureId)}>Применить окончательно <span>↗</span></button></div><p className="irreversible-note">Решение нельзя отменить. Убедитесь, что выбран правильный район и мера.</p></section></div>}
    <footer className="footer-note"><span>QALA SIMULATION SYSTEM</span><span>СИНТЕТИЧЕСКИЕ ДАННЫЕ · НЕ ПРОГНОЗ ДЛЯ РЕАЛЬНОГО ГОРОДА</span><span>BUILD 0.1</span></footer>
  </main>;
}
