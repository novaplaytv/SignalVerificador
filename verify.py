import os
import json
import requests
import time
import urllib3

# Silenciar advertencias de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_flow_token():
    """Simula la obtención de token que hace la App"""
    try:
        # Intentamos obtener el token desde tu API de respaldo (secreto)
        token_api = os.getenv("TOKEN_API_URL")
        if not token_api: return None

        res = requests.get(token_api, timeout=10, verify=False)
        if res.status_code == 200:
            data = res.json()
            # Estructura de tu token.json (intentar ambas variantes)
            return data.get("token") or data.get("value", {}).get("token")
    except:
        return None
    return None

def check_signal(name, url, headers, is_flow=False, token=None):
    try:
        # 1. Preparar URL y Headers
        test_url = url
        test_headers = headers.copy()

        # 2. Inyección de Token si es Flow
        if is_flow and token:
            if "[TOKEN]" in test_url:
                test_url = test_url.replace("[TOKEN]", token)
            elif "TOKEN_AQUÍ" in test_url:
                test_url = test_url.replace("TOKEN_AQUÍ", token)
            else:
                # Si no hay placeholder, inyectar por parámetro común si no lo tiene
                if "tok_" not in test_url and "token=" not in test_url:
                    separator = "&" if "?" in test_url else "?"
                    test_url += f"{separator}token={token}"

        # 3. Petición de verificación
        start_time = time.time()
        # Timeout extendido a 30s para redes lentas
        response = requests.get(test_url, headers=test_headers, timeout=30, stream=True, verify=False)
        elapsed = time.time() - start_time

        # 4. Validar contenido real (Peek de 2KB para DASH)
        content_peek = response.raw.read(2048).decode('utf-8', errors='ignore').upper()

        # Detección robusta de manifiestos
        is_m3u8 = "#EXTM3U" in content_peek
        is_mpd = "<MPD" in content_peek or "DASH+XML" in response.headers.get("Content-Type", "").upper()

        if response.status_code in [200, 206] and (is_m3u8 or is_mpd):
            return {"status": "ONLINE", "latency": f"{int(elapsed*1000)}ms", "code": response.status_code}
        elif response.status_code in [301, 302, 307, 308]:
            return {"status": "REDIRECT", "latency": f"{int(elapsed*1000)}ms", "code": response.status_code}
        else:
            # Si es 403 pero es Flow, quizás el token falló pero la señal es válida estructuralmente
            status = "OFFLINE"
            if response.status_code == 403 and is_flow: status = "PROTECTED"
            return {"status": status, "code": response.status_code}

    except Exception as e:
        return {"status": "ERROR", "msg": str(e)[:50]}

def main():
    source_url = os.getenv("JSON_SOURCE_URL")
    if not source_url:
        print("Error: JSON_SOURCE_URL no configurado.")
        return

    print("--- NovaPlay Signal Watchdog v2.0 ---")

    # Obtener token de sesión global para este ciclo
    flow_token = get_flow_token()
    if flow_token:
        print(f"✔ Token de sesión obtenido correctamente.")
    else:
        print(f"⚠ No se pudo obtener token. Los canales protegidos podrían fallar.")

    try:
        data = requests.get(source_url, verify=False).json()
        categories = data.get('value', data) if isinstance(data, dict) else data

        report = {
            "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
            "results": []
        }

        for cat in categories:
            cat_name = cat.get('title', 'Otros')
            for item in cat.get('items', []):
                url = item.get('url')
                if not url: continue

                is_flow = item.get('flow') == "yes" or "flow" in url.lower()

                headers = {
                    "User-Agent": item.get('User-Agent', "PlayTVPremium"),
                    "Origin": item.get('Origin', "https://portal.app.flow.com.ar"),
                    "Referer": item.get('Referer', "https://portal.app.flow.com.ar/")
                }

                print(f"[{cat_name}] {item.get('name')}...", end=" ", flush=True)
                res = check_signal(item.get('name'), url, headers, is_flow, flow_token)
                print(f"{res['status']} ({res.get('code', 'ERR')})")

                report["results"].append({
                    "id": item.get('canal'),
                    "name": item.get('name'),
                    "category": cat_name,
                    "status": res['status'],
                    "latency": res.get('latency', '-'),
                    "code": res.get('code', 0)
                })

        with open("status.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)

        print("\n✔ status.json generado con éxito.")

    except Exception as e:
        print(f"Fallo crítico: {e}")

if __name__ == "__main__":
    main()
