# 📚 ÍNDICE DE DOCUMENTACIÓN - Sistema INTRADIA

## 📖 Guía de Documentos

Este es el índice completo de documentación técnica del sistema de trading INTRADIA.

---

## 🎯 Documentos Esenciales (Leer Primero)

### 1. **`RESUMEN_FINAL_IMPLEMENTACION.md`** ⭐
**Qué contiene:** Resumen ejecutivo completo del sistema v2.0 optimizado
**Para quién:** Todos - Visión general rápida
**Tiempo:** 10 minutos de lectura

### 2. **`ESTRATEGIA_TECNICA_COMPLETA.md`** 📐
**Qué contiene:** Descripción matemática y técnica detallada (1069 líneas)
**Para quién:** Desarrolladores, analistas técnicos, investigadores
**Tiempo:** 30-45 minutos de estudio
**Incluye:**
- Arquitectura completa
- Fórmulas matemáticas
- Pseudocódigo detallado
- Diagramas de flujo
- Ejemplos numéricos

---

## 📊 Documentos de Implementación

### 3. **`MEJORAS_IMPLEMENTADAS.md`**
**Qué contiene:** Detalle de las 4 mejoras críticas implementadas
**Para quién:** Desarrolladores que necesitan entender los cambios
**Secciones:**
- Umbral elevado (4.0 → 5.5)
- Filtro EMA200
- Filtro de volatilidad
- Límite de operaciones diarias
- Impacto esperado

### 4. **`IMPLEMENTACION_FILTROS_ESTADISTICOS.md`**
**Qué contiene:** Documentación técnica de todos los filtros
**Para quién:** Desarrolladores implementando nuevas características
**Incluye:**
- Tabla de puntuación
- Ejemplos de señales
- Flujo de decisión

---

## 🔬 Documentos de Investigación

### 5. **`RESEARCH_ESTADISTICAS_FILTROS.md`**
**Qué contiene:** Investigación de ecuaciones estadísticas aplicables
**Para quién:** Investigadores, data scientists
**Incluye:**
- Ecuaciones de 10 métodos estadísticos
- Bandas de Bollinger
- Probabilidad Bayesiana
- T-test, Sharpe Ratio, Kelly Criterion
- Referencias académicas

### 6. **`RESUMEN_COMPLETACION_FASE3.md`**
**Qué contiene:** Estado técnico de implementación de filtros
**Para quién:** Desarrolladores (referencia interna)

---

## 📋 Archivos de Configuración

### 7. **`ESTRATEGIA_TRADING.md`**
**Qué contiene:** Estrategia base original (Zones → Sweep → Retest → Entry)
**Para quién:** Referencia histórica

### 8. **`ASSUMPTIONS.md`**
**Qué contiene:** Supuestos y decisiones de diseño del proyecto

---

## 🚀 Guías de Uso

### 9. **`README.md`**
**Qué contiene:** Documentación general del proyecto

### 10. Scripts de Utilidad:
- `scripts\reset_all_orders.py` - Reiniciar métricas
- `scripts\check_orders_status.py` - Ver estado de órdenes

---

## 🎓 Orden de Lectura Recomendado

### Si eres **TRADER**:
1. `RESUMEN_FINAL_IMPLEMENTACION.md`
2. `MEJORAS_IMPLEMENTADAS.md`
3. Scripts de uso

### Si eres **DESARROLLADOR**:
1. `RESUMEN_FINAL_IMPLEMENTACION.md`
2. `ESTRATEGIA_TECNICA_COMPLETA.md` (estudio completo)
3. `MEJORAS_IMPLEMENTADAS.md`
4. Archivos fuente: `rule_based.py`, `indicators.py`

### Si eres **RESEARCHER/ANALYST**:
1. `RESEARCH_ESTADISTICAS_FILTROS.md`
2. `ESTRATEGIA_TECNICA_COMPLETA.md` (Sección 6-11)
3. `MEJORAS_IMPLEMENTADAS.md` (Sección de T-test)

---

## 📂 Estructura de Archivos

```
INTRADIA/
├── 📄 Documentación
│   ├── ESTRATEGIA_TECNICA_COMPLETA.md ⭐⭐⭐
│   ├── RESUMEN_FINAL_IMPLEMENTACION.md ⭐⭐
│   ├── MEJORAS_IMPLEMENTADAS.md ⭐
│   ├── IMPLEMENTACION_FILTROS_ESTADISTICOS.md ⭐
│   ├── RESEARCH_ESTADISTICAS_FILTROS.md
│   ├── RESUMEN_COMPLETACION_FASE3.md
│   ├── ESTRATEGIA_TRADING.md
│   └── INDICE_DOCUMENTACION.md (este archivo)
│
├── 💻 Código Fuente
│   ├── market/
│   │   └── indicators.py ⭐⭐⭐ (9 filtros)
│   └── engine/services/
│       ├── rule_based.py ⭐⭐⭐ (decisión)
│       ├── rule_loop.py ⭐⭐ (ejecución)
│       ├── sweep_detector.py
│       └── zone_detector.py
│
└── 🛠️ Scripts
    ├── reset_all_orders.py
    ├── check_orders_status.py
    └── reset_metrics_auto.py
```

---

## 🎯 Búsqueda Rápida

### Quiero entender... ¿Dónde buscar?

**"¿Cómo funciona el sistema de puntuación?"**
→ `ESTRATEGIA_TECNICA_COMPLETA.md`, Sección 4

**"¿Qué mejoras se implementaron?"**
→ `MEJORAS_IMPLEMENTADAS.md`, Sección 1-4

**"¿Por qué mi win rate es 50%?"**
→ `RESUMEN_FINAL_IMPLEMENTACION.md`, Sección "Lógica Filosófica"

**"¿Cómo se calcula MACD?"**
→ `ESTRATEGIA_TECNICA_COMPLETA.md`, Sección 6.4

**"¿Cómo optimizar los pesos?"**
→ `RESEARCH_ESTADISTICAS_FILTROS.md`, Sección 9

**"¿Cómo reiniciar métricas?"**
→ `scripts\reset_all_orders.py`

**"¿Cómo validar que las mejoras funcionan?"**
→ `MEJORAS_IMPLEMENTADAS.md`, Sección "Validación"

**"¿Cuál es la lógica completa del flujo?"**
→ `ESTRATEGIA_TECNICA_COMPLETA.md`, Sección 9

---

## 📊 Estadísticas de Documentación

| Documento | Líneas | Temas Principales |
|-----------|--------|-------------------|
| `ESTRATEGIA_TECNICA_COMPLETA.md` | 1069 | Toda la arquitectura |
| `RESEARCH_ESTADISTICAS_FILTROS.md` | 400 | Ecuaciones estadísticas |
| `MEJORAS_IMPLEMENTADAS.md` | 350 | Optimizaciones v2.0 |
| `IMPLEMENTACION_FILTROS_ESTADISTICOS.md` | 250 | Sistema de filtros |
| `RESUMEN_FINAL_IMPLEMENTACION.md` | 200 | Visión ejecutiva |

**Total:** ~2300 líneas de documentación técnica

---

## ✅ Checklist de Entendimiento

### Nivel Básico:
- [ ] Leí `RESUMEN_FINAL_IMPLEMENTACION.md`
- [ ] Entiendo que el sistema usa Zones + Sweeps + Filtros
- [ ] Sé que el umbral es 5.5/11.0
- [ ] Comprendo que hay límite de 5 trades/día

### Nivel Intermedio:
- [Левое поле] Leí `ESTRATEGIA_TECNICA_COMPLETA.md` (Secciones 1-5)
- [ ] Entiendo el cálculo de MACD, RSI, Bollinger
- [ ] Comprendo el sistema de puntuación bayesiana
- [ ] Sé cómo funcionan los filtros EMA200 y Volatilidad
- [ ] Puedo explicar por qué se rechazan señales

### Nivel Avanzado:
- [ ] Leí todo `ESTRATEGIA_TECNICA_COMPLETA.md`
- [ ] Entiendo las fórmulas matemáticas
- [ ] Puedo modificar pesos del sistema bayesiano
- [ ] Comprendo T-test y validación estadística
- [ ] Sé optimizar parámetros con data real

---

## 🔄 Actualización de Documentos

- **v1.0**: Estrategia base (Zones + Sweeps + Engulfing)
- **v2.0**: Sistema bayesiano completo con 4 mejoras críticas

**Última actualización:** 2025-01-28

---

## 💬 Preguntas Frecuentes

**Q: ¿Cuál es el documento más importante?**
A: `ESTRATEGIA_TECNICA_COMPLETA.md` - Es el manual completo del sistema.

**Q: ¿Dónde está el código fuente?**
A: `market/indicators.py` (indicadores) y `engine/services/rule_based.py` (lógica)

**Q: ¿Cómo ajusto la selectividad?**
A: Modifica `UMBRAL_ENTRADA` en `rule_based.py` (línea ~242):
- 5.5 = Estándar
- 6.0 = Más selectivo
- 5.0 = Menos selectivo

**Q: ¿Cómo reinicio las métricas?**
A: Ejecuta `python scripts\reset_all_orders.py`

---

**Índice creado:** 2025-01-28  
**Versión del sistema:** 2.0.0
