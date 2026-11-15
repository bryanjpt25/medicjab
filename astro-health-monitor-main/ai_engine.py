import numpy as np
import tensorflow as tf
from tensorflow.keras import layers, models

class DenisAIEngine:
    def __init__(self, model_path="model_quantized.tflite"):
        """
        Inicializa el motor de IA de Denis. 
        Carga el intérprete TFLite para ejecución 100% local y offline.
        """
        self.model_path = model_path
        self.interpreter = None
        self.input_details = None
        self.output_details = None
        
        # Intentamos cargar el modelo TFLite si ya existe, si no, lo creamos/entrenamos de forma simulada
        self._load_or_create_model()

    def _load_or_create_model(self):
        """Simula la creación, entrenamiento y conversión a TFLite si no existe el archivo."""
        try:
            # Intentar cargar el interprete de TFLite
            self.interpreter = tf.lite.Interpreter(model_path=self.model_path)
            self.interpreter.allocate_tensors()
            self.input_details = self.interpreter.get_input_details()
            self.output_details = self.interpreter.get_output_details()
            print("[INFO]: Modelo TFLite cargado exitosamente.")
        except Exception as e:
            print("[WARN]: No se encontró el archivo .tflite. Generando modelo base de prueba...")
            self._build_and_convert_dummy_model()

    def _build_and_convert_dummy_model(self):
        """Construye una red 1D-CNN ligera y la convierte a TFLite (INT8 simulado)."""
        # Estructura 1D-CNN para procesar ventanas de ECG (ej. 216 muestras)
        model = models.Sequential([
            layers.Input(shape=(216, 1)),
            layers.Conv1D(16, kernel_size=5, activation='relu'),
            layers.MaxPooling1D(pool_size=2),
            layers.Conv1D(32, kernel_size=3, activation='relu'),
            layers.GlobalAveragePooling1D(),
            layers.Dense(16, activation='relu'),
            layers.Dense(1, activation='sigmoid') # 0: Normal, 1: Arritmia / Ventricular
        ])

        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        
        # Generamos datos sintéticos de entrenamiento rápido para inicializar pesos
        X_dummy = np.random.randn(100, 216, 1).astype(np.float32)
        y_dummy = np.random.randint(0, 2, size=(100, 1)).astype(np.float32)
        model.fit(X_dummy, y_dummy, epochs=1, batch_size=16, verbose=0)

        # Convertir a TensorFlow Lite con optimización (Quantization)
        converter = tf.lite.TFLiteConverter.from_keras_model(model)
        converter.optimizations = [tf.lite.Optimize.DEFAULT]
        tflite_model = converter.convert()

        # Guardar el archivo .tflite (pesará menos de 2MB)
        with open(self.model_path, "wb") as f:
            f.write(tflite_model)

        # Cargar el intérprete recién creado
        self.interpreter = tf.lite.Interpreter(model_path=self.model_path)
        self.interpreter.allocate_tensors()
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        print("[INFO]: Modelo creado, cuantizado y convertido a .tflite correctamente.")

    def predict_ecg_segment(self, segment_signal):
        """
        Recibe un arreglo NumPy (segmento de ECG procesado por Bryan),
        realiza la inferencia local y retorna la etiqueta y confianza.
        
        :param segment_signal: Arreglo 1D de tamaño 216 (o se ajusta automáticamente)
        :return: dict con {"prediction": "NORMAL" o "ARRHYTHMIA", "confidence": float}
        """
        # Asegurar forma correcta (1, 216, 1) que exige la CNN
        if len(segment_signal) != 216:
            # Ajustar tamaño por interpolación o padding básico si difiere
            segment_signal = np.resize(segment_signal, (216,))
            
        input_data = np.array(segment_signal, dtype=np.float32).reshape(1, 216, 1)

        # Ejecutar inferencia con TFLite
        self.interpreter.set_tensor(self.input_details[0]['index'], input_data)
        self.interpreter.invoke()
        
        output_data = self.interpreter.get_tensor(self.output_details[0]['index'])
        score = float(output_data[0][0])

        # Definir umbral de decisión (ej: > 0.5 es Arritmia/Ventricular)
        if score > 0.5:
            label = "ARRHYTHMIA"
            confidence = score * 100
        else:
            label = "NORMAL"
            confidence = (1.0 - score) * 100

        return {
            "prediction": label,
            "confidence": float(round(confidence, 2)),
            "raw_score": score
        }