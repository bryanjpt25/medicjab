import pandas as pd
import streamlit as st

import salud_espacial as se

st.set_page_config(page_title="Salud espacial", layout="wide")
ss = st.session_state

st.title("Salud espacial · peligro → biomarcadores → lógica")
st.caption("Módulo adicional del Astro Health Monitor. Soporte a la decisión de demostración con umbrales demo; "
           "no sustituye al médico de vuelo (CMO / flight surgeon).")
st.page_link("app.py", label="← Volver al panel de monitoreo")

# Telemetría de cabina del panel principal (si ya se abrió en esta sesión)
pkt = ss.get("pkt")
env = pkt["environment"] if pkt else None
cum_live = None
try:
    cum_live = float(ss.sim.last_full_analysis()["radiation"]["cum_msv"])
except Exception:
    pass

ESCENARIOS = {
    "Normal": dict(fase="0 g · Microgravedad", fc=62, temp=36.7, glu=92, pas=112, pad=72, animo=7, co2m=600, spe=False, pico=0.2),
    "Tormenta solar + estrés metabólico": dict(fase="0 g · Microgravedad", fc=98, temp=37.5, glu=165, pas=118, pad=76, animo=5, co2m=600, spe=True, pico=25.0),
    "Hipoglucemia + taquicardia": dict(fase="0 g · Microgravedad", fc=118, temp=36.6, glu=48, pas=105, pad=65, animo=4, co2m=600, spe=False, pico=0.2),
    "Aterrizaje: hipotensión ortostática": dict(fase="0,38 g · Marte", fc=112, temp=36.8, glu=90, pas=82, pad=55, animo=6, co2m=600, spe=False, pico=0.2),
    "CO₂ alto con malestar": dict(fase="0 g · Microgravedad", fc=102, temp=36.8, glu=90, pas=118, pad=76, animo=3, co2m=3500, spe=False, pico=0.2),
}


for _k, _v in ESCENARIOS["Normal"].items():
    ss.setdefault(_k, _v)


def aplicar(nombre):
    for k, v in ESCENARIOS[nombre].items():
        ss[k] = v


def show(alertas):
    for lvl, msg in alertas:
        {"error": st.error, "warning": st.warning, "success": st.success}.get(lvl, st.info)(msg)


def kb_block(clave, campos=("sintomas", "diagnostico", "tratamiento", "efectos")):
    kb = se.KB[clave]
    etiquetas = {"patologias": "Patologías", "sintomas": "Síntomas", "diagnostico": "Diagnóstico",
                 "tratamiento": "Tratamiento / cura", "efectos": "Efectos secundarios", "fuentes": "Fuentes"}
    with st.expander(f"Ficha clínica · {kb['titulo']}"):
        for c in campos:
            st.markdown(f"**{etiquetas[c]}**")
            st.markdown("\n".join(f"- {x}" for x in kb[c]))


with st.sidebar:
    st.header("Biomarcadores simulados")
    st.selectbox("Escenario rápido", list(ESCENARIOS), key="esc_sel")
    st.button("Cargar escenario", on_click=aplicar, args=(ss.get("esc_sel", "Normal"),))
    fase = st.selectbox("Fase gravitatoria", list(se.FASES), key="fase")
    fc = st.slider("FC en reposo (lpm)", 35, 180, key="fc")
    temp = st.slider("Temperatura corporal (°C)", 35.0, 40.5, key="temp", step=0.1)
    glu = st.slider("Glucosa en sangre (mg/dL)", 30, 300, key="glu")
    pas = st.slider("Presión sistólica (mmHg)", 60, 200, key="pas")
    pad = st.slider("Presión diastólica (mmHg)", 40, 130, key="pad")
    animo = st.slider("Estado de ánimo (1–10)", 1, 10, key="animo")
    st.divider()
    st.subheader("Cabina")
    usar_live = st.checkbox("Usar telemetría del panel principal", value=env is not None, disabled=env is None)
    if usar_live and env:
        co2, tcab, rad = env["co2_ppm"], env["temperature_c"], env["radiation_usv_h"]
        st.caption(f"CO₂ {co2:.0f} ppm · {tcab:.1f} °C · {rad:.2f} µSv/h")
    else:
        co2 = st.slider("CO₂ (ppm)", 300, 8000, key="co2m")
        tcab = st.slider("Temperatura de cabina (°C)", 10.0, 40.0, 22.5, 0.5)
        rad = st.slider("Radiación (µSv/h)", 0.0, 60.0, key="pico")
    ruido = st.slider("Ruido de cabina (dB)", 30, 90, 52)

tabs = st.tabs(["☢️ Radiación", "😴 Fatiga y circadiano", "🛰️ Triaje offline", "🧍 Gravedad y ortostatismo",
                "🫁 Ambiente + biometría", "📚 Base de conocimiento"])

# 1 · Radiación -------------------------------------------------------------
with tabs[0]:
    st.subheader("Correlación de evento solar (SPE) + estrés metabólico")
    c1, c2, c3 = st.columns(3)
    spe = c1.checkbox("Alerta de tormenta solar (SPE)", key="spe")
    horas = c2.slider("Horas de exposición al pico", 1, 72, 6)
    fc_min = c3.slider("Minutos con FC en reposo elevada", 0, 240, 45)
    dosis = st.number_input("Dosis acumulada (mSv)", 0.0, 2000.0, float(cum_live if cum_live is not None else 80.0), 5.0)
    r = se.evaluar_radiacion(dosis, rad, horas, spe, fc, fc_min, glu, temp)
    m = st.columns(3)
    m[0].metric("Dosis acumulada", f"{dosis:.0f} mSv", f"{r['limit_pct']:.0f}% del límite NASA", delta_color="off")
    m[1].metric("Dosis del evento", f"{r['dosis_evento_msv']:.2f} mSv")
    m[2].metric("Señales metabólicas", len(r["senales"]))
    show(r["alertas"] or [("success", "Sin correlación radiación–metabolismo.")])
    kb_block("radiacion")

# 2 · Fatiga ----------------------------------------------------------------
with tabs[1]:
    st.subheader("Índice de fatiga conductual y ritmo circadiano")
    st.caption("En órbita amanece cada ~90 min. Se marca el día con sueño <6 h, ánimo en caída y FC basal al alza; "
               "si la racha supera 3 días se activan intervenciones.")
    base = pd.DataFrame({"día": range(1, 8), "sueno": [7, 6.5, 5.5, 5, 5, 4.5, 5], "animo": [7, 6, 5, 5, 4, 4, 3],
                         "fc": [62, 64, 67, 68, 70, 71, 73], "vfc": [45, 43, 40, 38, 36, 34, 32]})
    ed = st.data_editor(base, hide_index=True, num_rows="fixed", key="fat_tab")
    f = se.evaluar_fatiga(ed.to_dict("records"))
    ed["índice de fatiga"] = f["indice"]
    marc = [str(d) for d, x in zip(ed["día"], f["marcados"]) if x]
    st.line_chart(ed.set_index("día")["índice de fatiga"], height=180)
    st.caption("Días marcados: " + (", ".join(marc) or "ninguno"))
    show(f["alertas"] or [("success", "Sin tendencia de fatiga sostenida.")])
    if f["intervenciones"]:
        st.markdown("**Intervenciones automáticas sugeridas:**")
        st.markdown("\n".join(f"{i}. {t}" for i, t in enumerate(f["intervenciones"], 1)))
    kb_block("aislamiento")

# 3 · Triaje offline ----------------------------------------------------------
with tabs[2]:
    st.subheader("Simulador de latencia y triaje autónomo (sin Houston)")
    destino = st.selectbox("Distancia a la Tierra", list(se.DIST_S), index=3)
    lat = se.latencia(se.DIST_S[destino])
    l = st.columns(3)
    l[0].metric("Retardo de ida", f"{lat['ida_s']:.1f} s")
    l[1].metric("Ida y vuelta", f"{lat['ida_vuelta_s'] / 60:.1f} min")
    l[2].metric("Respuesta de Tierra", "no esperar" if lat["autonomo"] else "útil")
    (st.error if lat["autonomo"] else st.info)(lat["modo"])
    t1, t2, t3 = st.columns(3)
    consciente = t1.checkbox("Tripulante consciente", value=True)
    vomitos = t2.checkbox("Vómitos")
    spo2 = t3.slider("SpO₂ (%)", 70, 100, 97)
    hits = se.triaje(glu, fc, pas, spo2, consciente, vomitos, co2, spe)
    if not hits:
        st.success("Sin criterios de emergencia en los biomarcadores actuales.")
    for prio, clave, motivo in hits:
        titulo, pasos = se.PROTOCOLOS[clave]
        with st.container(border=True):
            st.markdown(f"**Prioridad {prio} · {titulo}** — {motivo}")
            hechos = [st.checkbox(p, key=f"tri_{clave}_{i}") for i, p in enumerate(pasos)]
            st.progress(sum(hechos) / len(pasos), text=f"{sum(hechos)}/{len(pasos)} pasos completados")
    kb_block("distancia")

# 4 · Gravedad ----------------------------------------------------------------
with tabs[3]:
    st.subheader("Intolerancia ortostática y desplazamiento de fluidos")
    o1, o2 = st.columns(2)
    dias0g = o1.slider("Días previos en microgravedad", 0, 400, 45)
    with o2.expander("Referencia en supino (para el test ortostático)", expanded=True):
        s_pas = st.number_input("PAS supino", 60, 200, 118)
        s_pad = st.number_input("PAD supino", 40, 130, 74)
        s_fc = st.number_input("FC supino", 35, 180, 60)
    o = se.evaluar_ortostatico(fase, pas, pad, fc, dict(pas=s_pas, pad=s_pad, fc=s_fc), dias0g)
    rg = o["rangos"]
    st.dataframe(pd.DataFrame({"variable": ["PAS (mmHg)", "PAD (mmHg)", "FC (lpm)"],
                               f"rango normal · {fase}": [f"{rg['pas'][0]}–{rg['pas'][1]}", f"{rg['pad'][0]}–{rg['pad'][1]}",
                                                         f"{rg['fc'][0]}–{rg['fc'][1]}"],
                               "actual": [pas, pad, fc]}), hide_index=True)
    k = st.columns(4)
    k[0].metric("Δ PAS", f"{-o['delta']['dPAS']:.0f} mmHg")
    k[1].metric("Δ PAD", f"{-o['delta']['dPAD']:.0f} mmHg")
    k[2].metric("Δ FC", f"{o['delta']['dFC']:+.0f} lpm")
    k[3].metric("Riesgo ortostático", f"{o['riesgo']}/100")
    show(o["alertas"] or [("success", "Hemodinámica dentro del rango de la fase.")])
    kb_block("gravedad")

# 5 · Ambiente + biometría --------------------------------------------------------
with tabs[4]:
    st.subheader("Fusión ambiental-biométrica (ECLSS + salud)")
    fu = se.fusion_ambiental(fc, animo, temp, co2, tcab, ruido)
    st.markdown("**Orden de verificación antes de diagnosticar un problema cardíaco:**")
    ico = {"ok": "✅", "revisar": "⚠️", "pendiente": "🫀"}
    for n, (nombre, valor, est) in enumerate(fu["pasos"], 1):
        st.markdown(f"{n}. {ico[est]} **{nombre}**: {valor}")
    show(fu["alertas"] or [("success", "No hay patrón FC↑ + ánimo↓ que requiera cruzar con la cabina.")])
    kb_block("ambiente")

# 6 · Base de conocimiento -----------------------------------------------------------
with tabs[5]:
    st.subheader("Patologías inducidas por vuelos espaciales")
    st.dataframe(pd.DataFrame([{"peligro": v["titulo"], "patología": p} for v in se.KB.values() for p in v["patologias"]]),
                 hide_index=True)
    sel = st.selectbox("Peligro espacial", list(se.KB), format_func=lambda k: se.KB[k]["titulo"])
    kb = se.KB[sel]
    cols = st.columns(2)
    for i, (c, et) in enumerate((("sintomas", "Síntomas"), ("diagnostico", "Diagnóstico"),
                                 ("tratamiento", "Tratamiento / cura"), ("efectos", "Efectos secundarios (enfermedad y fármacos)"))):
        with cols[i % 2]:
            st.markdown(f"**{et}**")
            st.markdown("\n".join(f"- {x}" for x in kb[c]))
    st.caption("Fuentes: " + " · ".join(kb["fuentes"]))
