# Bot Reserva Automática Gimnasio USM (`reservasgimnasiosantiago.cl`)

Bot ligero en Python (sin dependencias externas) que se conecta directamente a la API de `https://reservasgimnasiosantiago.cl`, inicia sesión con tus credenciales y reserva tu bloque horario exacto a las **06:30:00 AM (hora de Chile)** mientras duermes.

## Horario Configurado ([`config.json`](./config.json))

- **Sede:** `Vitacura`
- **Lunes:** Bloque `7-8` (12:30 - 13:40)
- **Martes:** Bloque `11-12` (16:05 - 17:15)
- **Miércoles:** Sin reserva (`null`)
- **Jueves:** Bloque `7-8` (12:30 - 13:40)
- **Viernes:** Bloque `7-8` (12:30 - 13:40)

> Si algún semestre o semana quieres cambiar un bloque, solo edita [`config.json`](./config.json).

---

## Cómo activarlo gratis en la nube (GitHub Actions)

1. **Sube este proyecto a un repositorio en tu cuenta de GitHub** (puede ser privado o público).
2. En tu repositorio de GitHub, entra a **Settings** → **Secrets and variables** → **Actions** → **New repository secret** y agrega estos 2 secretos:
   - `GYM_EMAIL`: tu correo USM (ej. `nombre.apellido@usm.cl` o `@sansano.usm.cl`)
   - `GYM_PASSWORD`: tu contraseña de `reservasgimnasiosantiago.cl`
3. Ve a la pestaña **Actions** de tu repositorio, selecciona **Reserva Automática Gimnasio USM** → haz clic en **Run workflow** con el modo `test-login` para verificar que tus credenciales funcionan y ver los cupos actuales.

---

## Pruebas desde tu Mac (Opcional)

1. Crea tu archivo `.env`:
   ```bash
   cp .env.example .env
   ```
   Edita `.env` con tu correo y contraseña.
2. Prueba el login y consulta los cupos actuales:
   ```bash
   python3 bot.py --test-login
   ```
3. Para reservar de inmediato (cuando ya son más de las 06:30 AM):
   ```bash
   python3 bot.py --now
   ```
