import streamlit as st

from shared import load_bridge

st.set_page_config(page_title="Evaluación mental", layout="centered")

FREQ = {0: "0 · Nunca", 1: "1 · Varios días",
        2: "2 · Más de la mitad de los días", 3: "3 · Casi todos los días"}

st.title("Evaluación mental")
st.caption("Cuestionario breve PHQ-2 / GAD-2 + ítem de seguridad (PHQ-9, ítem 9). "
           "Soporte a la decisión de demostración, no sustituye a un profesional.")

bridge = load_bridge()
if isinstance(bridge, str):
    st.error(f"Gemelo bio-digital no disponible: {bridge[:200]}")
    st.stop()

st.page_link("app.py", label="← Volver al panel de monitoreo")
st.subheader("En las últimas 2 semanas, ¿con qué frecuencia le han molestado...?")

with st.form("psych_form"):
    p1 = st.radio("Poco interés o placer en hacer las cosas",
                  list(FREQ), format_func=FREQ.get, horizontal=True)
    p2 = st.radio("Sentirse decaído, deprimido o sin esperanza",
                  list(FREQ), format_func=FREQ.get, horizontal=True)
    g1 = st.radio("Sentirse nervioso, ansioso o con los nervios de punta",
                  list(FREQ), format_func=FREQ.get, horizontal=True)
    g2 = st.radio("No poder parar o controlar la preocupación",
                  list(FREQ), format_func=FREQ.get, horizontal=True)
    p9 = st.radio("Pensamientos de que estaría mejor muerto o de hacerse daño",
                  list(FREQ), format_func=FREQ.get, horizontal=True)
    sent = st.form_submit_button("Enviar evaluación", type="primary")

if sent:
    res = bridge.submit_psych({"phq2_score": p1 + p2,
                               "gad2_score": g1 + g2,
                               "phq9_item9": p9})
    if "error" in res:
        st.error(res["error"])
    else:
        st.success(f"Evaluación enviada · PHQ-2: {p1 + p2}/6 · GAD-2: {g1 + g2}/6")
        c1, c2 = st.columns(2)
        c1.metric("Nivel del gemelo", res["level"])
        mi = res.get("mental_index")
        c2.metric("Índice mental", "—" if mi is None else f"{mi:.2f}")

        if p9 > 0:
            st.error("Respuesta de seguridad registrada: se requiere contacto clínico "
                     "urgente y acompañamiento a la persona.")

        opts = bridge._options()
        if opts:
            st.markdown("**Contramedidas propuestas por el gemelo:**")
            for o in opts[:5]:
                extra = " · requiere médico" if o["requires_clinician"] else ""
                st.markdown(f"- **{o['label']}**{extra}: {o['benefits']}")
        st.info("El resultado también se refleja en el panel de monitoreo.")