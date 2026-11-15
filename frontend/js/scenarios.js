// Solo presentación. Los valores de cada escenario (FC, PA, glucosa, alertas…) ahora los calcula
// el backend: ver backend/scenarios.py (qué hace cada botón) y backend/runtime.py (motores).
export const organLabels = {
  heart: 'Diagnóstico Regional: Tórax / Cardíaco',
  abdomen: 'Diagnóstico Regional: Abdomen / Metabólico',
  legs: 'Diagnóstico Regional: Extremidades / Retorno Venoso'
};

export const defaultOrganText =
  'Selecciona los marcadores sobre la anatomía 3D para consultar el impacto fisiológico.';
