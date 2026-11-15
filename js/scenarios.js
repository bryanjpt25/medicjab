// Escenarios de simulación y sus valores.
// Edita este archivo para agregar o modificar escenarios.
export const dataModes = {
      normal: {
        bannerClass: '',
        bannerText: 'ESTADO: NOMINAL',
        commsTitle: 'Enlace con Tierra: nominal (1.2s)',
        commsSub: 'Escenario de cabina: NOMINAL',
        fc: 72, fcClass: '', fcDesc: 'Ritmo sinusal estable',
        sueno: 7.2, suenoColor: '#22c55e',
        pa: [118, 76], paClass: '', paDesc: 'Perfusión sistémica normal',
        glu: 92, gluClass: '', gluDesc: 'Control glucémico óptimo',
        temp: '36.6', tempClass: '', tempDesc: 'Termorregulación estable',
        iaClass: '', iaTitle: 'NOMINAL', iaDesc: '98% confianza · Sin anomalías',
        animoClass: '', animoVal: 'Estable · Óptimo (9/10)', animoDesc: 'Sin signos de fatiga cognitiva',
        radClass: '', radVal: '18.41', radDesc: 'Sesión: 6.32 µSv',
        pts: { heart: '', abdomen: '', legs: '' },
        organs: {
          heart: 'Frecuencia cardíaca en reposo normal (72 bpm) y variabilidad HRV saludable.',
          abdomen: 'Niveles de glucosa en sangre estables (92 mg/dL) sin estrés metabólico.',
          legs: 'Distribución de fluidos adaptada a microgravedad orbital.'
        }
      },
      radiacion: {
        bannerClass: 'critico',
        bannerText: 'ESTADO: CRÍTICO',
        commsTitle: 'Enlace con Tierra: intermitente',
        commsSub: 'Escenario de cabina: TORMENTA SOLAR (SPE)',
        fc: 129, fcClass: 'crit', fcDesc: 'Taquicardia / HRV crítica',
        sueno: 5.0, suenoColor: '#f59e0b',
        pa: [136, 88], paClass: 'warn', paDesc: 'Elevación tensional por estrés agudo',
        glu: 154, gluClass: 'warn', gluDesc: 'Hiperglucemia por estrés oxidativo',
        temp: '38.2', tempClass: 'crit', tempDesc: 'Febrícula por radiación ionizante',
        iaClass: 'crit', iaTitle: 'RADIACIÓN SPE', iaDesc: '94% confianza · Refugio blindado',
        animoClass: 'crit', animoVal: 'Fatiga Aguda / Náuseas (4/10)', animoDesc: 'Síndrome prodrómico: hidratar y resguardar',
        radClass: 'crit', radVal: '148.60', radDesc: '⚠️ +130.1 mSv en evento actual',
        pts: { heart: 'crit', abdomen: 'warn', legs: '' },
        organs: {
          heart: 'Taquicardia sostenida (129 bpm) e inflamación endotelial por protones solares.',
          abdomen: 'Estrés oxidativo eleva glucosa a 154 mg/dL; riesgo de náuseas agudas.',
          legs: 'Sin compromiso vascular periférico.'
        }
      },
      aislamiento: {
        bannerClass: 'alerta',
        bannerText: 'ESTADO: ALERTA',
        commsTitle: 'Enlace con Tierra: nominal (1.4s)',
        commsSub: 'Escenario de cabina: DESINCRONIZACIÓN CIRCADIANA',
        fc: 88, fcClass: 'warn', fcDesc: 'HRV reducida por fatiga acumulada',
        sueno: 3.8, suenoColor: '#ef4444',
        pa: [126, 82], paClass: '', paDesc: 'Límite superior normal',
        glu: 114, gluClass: 'warn', gluDesc: 'Cortisol elevado por déficit de sueño',
        temp: '36.5', tempClass: '', tempDesc: 'Normal',
        iaClass: 'warn', iaTitle: 'FATIGA CIRCADIANA', iaDesc: '89% confianza · Ajustar luz 2700K',
        animoClass: 'crit', animoVal: 'Ansioso / Irritable (3/10)', animoDesc: '16 amaneceres/día alteran ciclo de melatonina',
        radClass: '', radVal: '19.12', radDesc: 'Sesión: 6.40 µSv',
        pts: { heart: 'warn', abdomen: '', legs: '' },
        organs: {
          heart: 'Reducción de variabilidad cardíaca (HRV) por falta de descanso reparador.',
          abdomen: 'Ligera resistencia insulínica matutina por privación de sueño (<4h).',
          legs: 'Tono muscular estable.'
        }
      },
      distancia: {
        bannerClass: 'critico',
        bannerText: 'ESTADO: CRÍTICO',
        commsTitle: 'Enlace con Tierra: BLACKOUT (22m)',
        commsSub: 'Escenario: ESPACIO PROFUNDO · SIN SOPORTE TIERRA',
        fc: 126, fcClass: 'crit', fcDesc: 'Taquicardia compensatoria',
        sueno: 5.8, suenoColor: '#f59e0b',
        pa: [90, 56], paClass: 'warn', paDesc: 'Hipotensión moderada',
        glu: 51, gluClass: 'crit', gluDesc: 'HIPOGLUCEMIA SEVERA (<60 mg/dL)',
        temp: '35.9', tempClass: 'warn', tempDesc: 'Descenso térmico periférico',
        iaClass: 'crit', iaTitle: 'TRIAJE OFFLINE', iaDesc: '96% confianza · Dar 15g glucosa',
        animoClass: 'crit', animoVal: 'Confusión / Mareo (3/10)', animoDesc: 'Autonomía médica local activa sin Houston',
        radClass: 'warn', radVal: '64.20', radDesc: 'Tránsito interplanetario',
        pts: { heart: 'crit', abdomen: 'crit', legs: '' },
        organs: {
          heart: 'Taquicardia adrenérgica (126 bpm) disparada por caída crítica de glucosa.',
          abdomen: 'Hipoglucemia severa (51 mg/dL). Requiere glucosa oral inmediata.',
          legs: 'Debilidad generalizada.'
        }
      },
      gravedad: {
        bannerClass: 'critico',
        bannerText: 'ESTADO: CRÍTICO',
        commsTitle: 'Enlace con Tierra: latencia 14 min',
        commsSub: 'Escenario: ATERRIZAJE MARTE (0g → 0.38g)',
        fc: 135, fcClass: 'crit', fcDesc: 'Taquicardia ortostática refleja',
        sueno: 6.6, suenoColor: '#22c55e',
        pa: [78, 48], paClass: 'crit', paDesc: 'INTOLERANCIA ORTOSTÁTICA AGUDA',
        glu: 90, gluClass: '', gluDesc: 'Normal',
        temp: '36.4', tempClass: '', tempDesc: 'Normal',
        iaClass: 'crit', iaTitle: 'HIPOTENSIÓN 0.38G', iaDesc: '95% confianza · Activar traje anti-G',
        animoClass: 'warn', animoVal: 'Aturdimiento / Visión Túnel (5/10)', animoDesc: 'Desplazamiento venoso hacia extremidades inferiores',
        radClass: 'warn', radVal: '82.15', radDesc: 'Dosis acumulada de tránsito',
        pts: { heart: 'crit', abdomen: '', legs: 'crit' },
        organs: {
          heart: 'Disparo compensatorio a 135 bpm para mantener perfusión cerebral en 0.38g.',
          abdomen: 'Parámetros metabólicos estables.',
          legs: 'Acumulación súbita de sangre en miembros inferiores tras meses en 0g.'
        }
      },
      entorno: {
        bannerClass: 'alerta',
        bannerText: 'ESTADO: ALERTA',
        commsTitle: 'Enlace con Tierra: intermitente',
        commsSub: 'Escenario de cabina: FUGA DE CO₂ (ECLSS)',
        fc: 108, fcClass: 'warn', fcDesc: 'Taquicardia por hipercapnia leve',
        sueno: 5.4, suenoColor: '#f59e0b',
        pa: [138, 88], paClass: 'warn', paDesc: 'Vasodilatación cerebral / PA alta',
        glu: 97, gluClass: '', gluDesc: 'Normal',
        temp: '37.5', tempClass: 'warn', tempDesc: 'Estrés térmico en módulo cerrado',
        iaClass: 'warn', iaTitle: 'ALERTA CO₂ CABINA', iaDesc: '91% confianza · Purgar filtros LiOH',
        animoClass: 'crit', animoVal: 'Cefalea / Letargo (4/10)', animoDesc: 'Fusión cabina-salud: ppCO₂ > 6.5 mmHg',
        radClass: '', radVal: '18.95', radDesc: 'Sesión: 6.35 µSv',
        pts: { heart: 'warn', abdomen: '', legs: '' },
        organs: {
          heart: 'Aumento de gasto cardíaco y frecuencia respiratoria por exceso de CO₂.',
          abdomen: 'Sin alteración glucémica.',
          legs: 'Normal.'
        }
      }
    };
