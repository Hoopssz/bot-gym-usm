#!/usr/bin/env python3
"""
Bot de Reserva Automática - Gimnasio USM (https://reservasgimnasiosantiago.cl)
Sin dependencias externas (usa únicamente la librería estándar de Python 3.9+).
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE_URL = "https://reservasgimnasiosantiago.cl"
CHILE_TZ = ZoneInfo("America/Santiago")

BLOQUES_HORARIOS = {
    "1-2": "08:15 - 09:25",
    "3-4": "09:40 - 10:50",
    "5-6": "11:05 - 12:15",
    "7-8": "12:30 - 13:40",
    "9-10": "14:40 - 15:50",
    "11-12": "16:05 - 17:15",
    "13-14": "17:30 - 18:40",
    "15-16": "18:55 - 20:05",
}

DIAS_ES = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miércoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sábado",
    "sunday": "Domingo",
}


def load_dotenv(env_path: Path) -> None:
    """Carga variables desde un archivo .env si existe."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def now_chile() -> datetime:
    return datetime.now(CHILE_TZ)


def log(msg: str) -> None:
    ts = now_chile().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    print(f"[{ts} CL] {msg}", flush=True)


class GymUSMClient:
    def __init__(self, base_url: str = BASE_URL) -> None:
        self.base_url = base_url.rstrip("/")
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar)
        )
        self.default_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
        }

    def request(self, method: str, path: str, payload: dict | None = None) -> tuple[bool, int, dict | str]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in self.default_headers.items():
            req.add_header(k, v)

        try:
            with self.opener.open(req, timeout=15) as resp:
                status = resp.status
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = raw
                return (200 <= status < 300), status, parsed
        except urllib.error.HTTPError as err:
            raw = err.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"error": raw}
            return False, err.code, parsed
        except Exception as exc:
            return False, 500, {"error": str(exc)}

    def login(self, email: str, password: str) -> tuple[bool, dict]:
        ok, status, data = self.request(
            "POST", "/api/login", {"username": email, "password": password}
        )
        if ok and isinstance(data, dict) and data.get("user"):
            return True, data
        err_msg = data.get("error") if isinstance(data, dict) else str(data)
        return False, {"status": status, "error": err_msg or "Credenciales inválidas"}

    def get_mis_reservas(self) -> list[dict]:
        ok, _, data = self.request("GET", "/api/reservas")
        if ok and isinstance(data, dict):
            return data.get("reservas") or []
        return []

    def get_cupos(self, sede: str | None = None) -> dict:
        path = "/api/cupos"
        if sede:
            path += f"?sede={urllib.parse.quote(sede)}"
        ok, _, data = self.request("GET", path)
        return data if (ok and isinstance(data, dict)) else {}

    def reservar(self, bloque_horario: str, sede: str) -> tuple[bool, int, dict]:
        ok, status, data = self.request(
            "POST",
            "/api/reservas",
            {"bloque_horario": bloque_horario, "sede": sede},
        )
        if not isinstance(data, dict):
            data = {"message": str(data)}
        return ok, status, data


def wait_until(target_dt: datetime) -> None:
    """Espera con precisión hasta target_dt (hora de Chile)."""
    while True:
        current = now_chile()
        remaining = (target_dt - current).total_seconds()
        if remaining <= 0:
            break
        if remaining > 60:
            log(f"Esperando apertura... faltan {remaining / 60:.1f} minutos para {target_dt.strftime('%H:%M:%S')}")
            time.sleep(min(30.0, remaining - 15.0))
        elif remaining > 2:
            log(f"Preparando disparo... faltan {remaining:.1f} segundos")
            time.sleep(remaining - 1.5)
        else:
            time.sleep(max(0.01, remaining / 2))


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    load_dotenv(base_dir / ".env")

    parser = argparse.ArgumentParser(description="Bot de Reservas Gimnasio USM")
    parser.add_argument(
        "--test-login",
        action="store_true",
        help="Prueba el inicio de sesión y muestra los cupos actuales sin reservar.",
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Intenta reservar inmediatamente sin esperar a las 06:30:00 AM.",
    )
    parser.add_argument(
        "--bloque",
        type=str,
        default=None,
        help="Fuerza un bloque horario específico (ej: 7-8, 11-12).",
    )
    parser.add_argument(
        "--sede",
        type=str,
        default=None,
        help="Fuerza una sede específica (Vitacura o San Joaquín).",
    )
    args = parser.parse_args()

    config_path = base_dir / "config.json"
    if not config_path.exists():
        log(f"❌ No se encontró {config_path}")
        return 1

    config = json.loads(config_path.read_text(encoding="utf-8"))
    sede = args.sede or config.get("sede", "Vitacura")

    email = os.environ.get("GYM_EMAIL", "").strip()
    password = os.environ.get("GYM_PASSWORD", "").strip()

    if not email or not password:
        log("❌ Faltan las credenciales GYM_EMAIL o GYM_PASSWORD.")
        log("   Configúralas en el archivo .env (local) o en GitHub Secrets (nube).")
        return 1

    client = GymUSMClient()

    if args.test_login:
        log(f"Probando inicio de sesión para {email}...")
        ok, info = client.login(email, password)
        if not ok:
            log(f"❌ Error de login: {info.get('error')} (HTTP {info.get('status')})")
            return 1
        user = info.get("user", {})
        log(f"✅ Login exitoso: {user.get('name')} ({user.get('email')}) - Rol: {user.get('role_type')}")
        reservas = client.get_mis_reservas()
        log(f"📋 Reservas activas hoy ({len(reservas)}): {reservas}")
        cupos = client.get_cupos(sede)
        log(f"🏋️ Cupos actuales en {sede}:")
        for key, c in sorted(cupos.items(), key=lambda x: int(x[1]["bloque"].split("-")[0])):
            if c.get("sede") == sede:
                b = c["bloque"]
                horario = BLOQUES_HORARIOS.get(b, "")
                log(f"   • Bloque {b:5s} ({horario}): {c['disponibles']}/{c['total']} disponibles")
        return 0

    # Determinar el bloque del día según la hora de Chile
    today_cl = now_chile()
    if not args.now and (today_cl.hour < 5 or (today_cl.hour == 5 and today_cl.minute < 45)):
        log(
            f"ℹ️ Son las {today_cl.strftime('%H:%M')} en Chile (horario de invierno UTC-4). "
            "Esta ejecución corresponde al cron de verano; el cron de las 06:xx AM CL ejecutará la reserva en 1 hora."
        )
        return 0

    day_key = today_cl.strftime("%A").lower()
    dia_nombre = DIAS_ES.get(day_key, day_key)

    bloque_principal = args.bloque or config.get("horarios_por_dia", {}).get(day_key)
    bloques_alt = config.get("bloques_alternativos_por_dia", {}).get(day_key, [])

    if not bloque_principal:
        log(f"ℹ️ Hoy es {dia_nombre}: configurado como 'No reservar'. Saliendo.")
        return 0

    bloques_a_intentar = [bloque_principal] + [
        b for b in bloques_alt if b and b != bloque_principal
    ]
    log(
        f"📅 Día: {dia_nombre} | Sede: {sede} | "
        f"Bloque objetivo: {bloque_principal} ({BLOQUES_HORARIOS.get(bloque_principal, '')})"
    )

    # 1. Login inicial para verificar credenciales y si ya existe reserva hoy
    log(f"Autenticando como {email}...")
    ok, login_data = client.login(email, password)
    if not ok:
        log(f"❌ Falló la autenticación inicial: {login_data.get('error')}")
        return 1
    log(f"✅ Sesión iniciada correctamente ({login_data['user'].get('name')})")

    reservas_actuales = client.get_mis_reservas()
    if reservas_actuales:
        log(f"✅ Ya tienes una reserva registrada para hoy: {reservas_actuales}")
        return 0

    # 2. Si se ejecuta antes de las 06:30:00 AM (y no se pasó --now), esperar y re-autenticar a las 06:29:45
    if not args.now:
        now = now_chile()
        open_time = now.replace(hour=6, minute=30, second=0, microsecond=0)
        warmup_time = open_time - timedelta(seconds=15)  # 06:29:45
        fire_time = open_time - timedelta(milliseconds=600)  # 06:29:59.400

        # Si el cron de respaldo de cambio de hora se ejecutó después de las 07:00 AM y ya pasó la ventana
        if now > open_time + timedelta(minutes=30):
            log("ℹ️ Ejecución posterior a las 07:00 AM. Intentando reservar de inmediato por si quedan cupos...")
        elif now < open_time:
            if now < warmup_time:
                wait_until(warmup_time)
                log("🔄 Refrescando sesión a las 06:29:45 para asegurar cookie activa...")
                client.login(email, password)
            wait_until(fire_time)

    # 3. Bucle de reserva de alta velocidad a las 06:30:00 AM
    max_attempts = 90 if not args.now else 5
    delay_seconds = 0.35

    for bloque in bloques_a_intentar:
        log(f"🚀 Iniciando intentos de reserva para Bloque {bloque} en {sede}...")
        for attempt in range(1, max_attempts + 1):
            ok, status, resp = client.reservar(bloque, sede)
            msg = resp.get("message") or resp.get("error") or str(resp)

            if ok:
                log(f"🎉 ¡RESERVA EXITOSA en intento #{attempt}! Bloque {bloque} ({BLOQUES_HORARIOS.get(bloque, '')}) - {sede}")
                log(f"   Respuesta del servidor: {msg}")
                return 0

            msg_lower = str(msg).lower()
            log(f"   [Intento #{attempt}/{max_attempts}] HTTP {status}: {msg}")

            # Si ya tiene una reserva hecha
            if "ya tienes" in msg_lower or "ya posee" in msg_lower or "máximo" in msg_lower:
                log("✅ El servidor indica que ya tienes una reserva activa para hoy.")
                return 0

            # Si el bloque se quedó sin cupos, pasar al bloque alternativo (si hay)
            if "sin cupos" in msg_lower or "no quedan cupos" in msg_lower or "agotado" in msg_lower:
                log(f"⚠️ Bloque {bloque} sin cupos disponibles.")
                break

            # Si la sesión expiró, re-autenticar rápido
            if status == 401:
                log("🔄 Re-autenticando sesión...")
                client.login(email, password)

            if attempt < max_attempts:
                time.sleep(delay_seconds)

    # Verificación final por si alguna petición entró justo en un timeout
    reservas_finales = client.get_mis_reservas()
    if reservas_finales:
        log(f"🎉 Confirmado en Mis Reservas: {reservas_finales}")
        return 0

    log("❌ No fue posible completar la reserva tras todos los intentos.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
