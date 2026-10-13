# Instrucciones permanentes para Claude

## Fuentes de verdad

1. Lee `DOCS.MD` para conocer el alcance funcional, los algoritmos y los criterios de aceptación.
2. Lee `docs/ESPECIFICACIONES_BACKEND.md` para las reglas técnicas del backend.
3. Lee `docs/ESPECIFICACIONES_FRONTEND.md` para las reglas técnicas del frontend.
4. Este archivo define cómo trabajar en el repositorio. Si hay contradicción entre documentos, no elijas silenciosamente: identifica el conflicto y solicita una decisión cuando afecte negocio, arquitectura, seguridad o alcance.

## Estructura obligatoria

- Backend: `APP/Backend/`.
- Frontend: `APP/Frontend/`.
- Infraestructura: `infra/`.
- Documentación y registros: `docs/`.
- Especificación maestra: `DOCS.MD`.

No cambies estos nombres ni fusiones backend y frontend. En Docker, scripts, CI y documentación usa las rutas reales de esta estructura.

## Protocolo de trabajo

- En una sesión inicial o cuando se solicite una nueva fase, inspecciona primero el workspace y los archivos relacionados. No asumas que el archivo o herramienta existe: compruébalo.
- En la primera ejecución, presenta un plan breve que incluya fases, estructura, dependencias, criterios de aceptación y riesgos. Espera aprobación explícita antes de programar, instalar, borrar o sobrescribir archivos.
- Después de la aprobación, trabaja en incrementos verticales pequeños. Antes de cada cambio revisa el código existente y preserva lo que funciona.
- No hagas una reescritura masiva del repositorio salvo aprobación explícita y justificación técnica.
- Pregunta cuando una decisión afecte reglas de negocio, arquitectura, seguridad, datos o alcance. Para detalles menores, elige una solución sencilla y mantenible y documenta contexto, decisión y consecuencias en `docs/DECISIONES.md`.
- Actualiza `docs/ESTADO_IMPLEMENTACION.md` al terminar cada incremento significativo.
- No avances ocultando pruebas fallidas ni bloqueos críticos. Resume qué falta y cuál es la siguiente acción segura.

## Calidad y honestidad

- No digas “funciona”, “está probado”, “seguro” o “completo” sin evidencia acorde. Enumera los comandos efectivamente ejecutados y su salida/resumen real.
- Distingue explícitamente entre implementado, probado, parcialmente implementado, pendiente y `DEMO-ONLY`.
- Si no puedes ejecutar Docker, pruebas de integración, auditorías o comandos por limitaciones del entorno, dilo y no marques el criterio como aprobado.
- No inventes archivos de resultados, cobertura, métricas de ML ni cumplimiento OWASP.
- Ejecuta las pruebas relacionadas con cada cambio; en hitos y al cierre ejecuta la batería integral pertinente.
- No reduzcas pruebas, desactives controles o cambies criterios de aceptación solo para conseguir una ejecución verde.
- Para datos sin planilla fuente, usa fixtures sintéticos reproducibles y casos manuales. Nunca digas que reprodujiste resultados de negocio de una planilla ausente.

## Arquitectura

- Respeta arquitectura hexagonal y SOLID según `DOCS.MD` y los documentos técnicos.
- El dominio no conoce FastAPI, SQLAlchemy, scikit-learn, Redis, red, filesystem ni adaptadores.
- La aplicación depende del dominio y de puertos, no de implementaciones.
- Los adaptadores no se importan entre sí; `bootstrap` conecta dependencias.
- Reglas de dependencia deben quedar verificadas por import-linter y pruebas de arquitectura.
- No uses singletons mutables/globales para estado específico de tenant, petición o simulación.
- ORM, modelos HTTP y entidades de dominio son tipos distintos con mapeos explícitos.

## Multi-tenancy y seguridad

- Usa tres servicios PostgreSQL en el demo: `pg-control`, `pg-tenant-a` y `pg-tenant-b`.
- Nunca decidas el tenant usando un `tenant_id` libre del cuerpo, query string o cabecera del usuario. El contexto confiable procede de la identidad autenticada y el registro central.
- Asegura el contexto de tenant en HTTP, tareas programadas, WebSockets/SSE, caché, archivos de ML, exportaciones, logs y jobs.
- No registres contraseñas, tokens, secretos, cadenas de conexión ni coordenadas/datos personales innecesarios.
- Los secretos no viven en Git; `.env.example` contiene únicamente nombres de variables y placeholders no funcionales.
- Deniega por defecto, valida autorización y pertenencia del objeto y conserva auditoría de cambios relevantes.
- Nunca marques un control OWASP implementado sin control de código y prueba/evidencia identificable.

## Código de demo y datos

- Todo simulador/proveedor falso debe estar detrás de un puerto y señalado con `DEMO-ONLY` en el código y `docs/DEUDA_DEMO.md`.
- Marca los datos del demo como **DATOS DE DEMOSTRACIÓN** en la interfaz.
- Fija las semillas aleatorias y permite reproducir las simulaciones.
- No llames a servicios pagos ni exijas API keys para iniciar la demo básica.
- No acoples reglas de negocio a la geografía, nombres o identidad de una empresa usada en la demostración.

## Dependencias y comandos

- Usa versiones fijadas y lockfiles cuando corresponda; registra por qué se incorpora una dependencia.
- No instales dependencias ni ejecutes operaciones destructivas antes de la aprobación del plan inicial.
- No expongas puertos de bases de datos al exterior sin necesidad documentada.
- Mantén comandos reproducibles para arranque, seed, pruebas, lint, seguridad y demo.

## Informe al terminar una fase

Resume: funcionalidades, archivos afectados, decisiones, comandos ejecutados, resultados reales, pruebas/cobertura, hallazgos de seguridad, limitaciones, deuda y estado de los criterios de aceptación. Incluye el siguiente paso recomendado sin empezar una nueva fase que requiera aprobación.
