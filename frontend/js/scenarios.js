// Presentation only. The values of each scenario (HR, BP, glucose, alerts…) are now computed by
// the backend: see backend/scenarios.py (what each button does) and backend/runtime.py (engines).
export const organLabels = {
  heart: 'Regional Diagnosis: Chest / Cardiac',
  abdomen: 'Regional Diagnosis: Abdomen / Metabolic',
  legs: 'Regional Diagnosis: Extremities / Venous Return'
};

export const defaultOrganText =
  'Select the markers on the 3D anatomy to view the physiological impact.';
