import os
import json
import requests
import time

def check_signal(name, url, headers):
    try:
        # Timeout extendido para señales lentas
        start_time = time.time()
        response = requests.get(url, headers=headers, timeout=15, stream=True)
        elapsed = time.time() - start_time

        # Validar si es un manifiesto real (no un error 200 con HTML de error)
        content_peek = response.raw.read(1024).decode('utf-8', errors='ignore').upper()

        is_valid = "#EXTM3U" in content_peek or "<MPD" in content_peek

        if response.status_code == 200 and is_valid:
            return {"status": "ONLINE", "latency": f"{int(elapsed*1000)}ms", "code": 200}
        elif response.status_code in [301, 302]:
            return {"status": "REDIRECT", "latency": f"{int(elapsed*1000)}ms", "code": response.status_code}
        else:
            return {"status": "OFFLINE", "code": response.status_code}

    except Exception as e:
        return {"status": "ERROR", "msg": str(e)[:50]}

def main():
    # Recuperar URL sensible desde el entorno (Secret)
    source_url = os.getenv("JSON_SOURCE_URL")
    if not source_url:
        print("Error: No se encontró la URL fuente en los Secrets.")
        return

    print("--- Iniciando Ciclo de Monitoreo NovaPlay ---")

    try:
        data = requests.get(source_url).json()
        # Manejar tanto formato array directo como objeto con 'value'
        categories = data.get('value', data) if isinstance(data, dict) else data

        report = {
            "last_update": time.strftime("%Y-%m-%d %H:%M:%S"),
            "results": []
        }

        for cat in categories:
            cat_name = cat.get('title', 'Sin Categoría')
            for item in cat.get('items', []):
                url = item.get('url')
                if not url or not any(ext in url.lower() for ext in ['.m3u8', '.mpd', '.m3u']):
                    continue

                headers = {
                    "User-Agent": item.get('User-Agent', "Mozilla/5.0"),
                    "Origin": item.get('Origin', ""),
                    "Referer": item.get('Referer', "")
                }

                print(f"Verificando: {item.get('name')}...", end=" ", flush=True)
                res = check_signal(item.get('name'), url, headers)
                print(res['status'])

                report["results"].append({
                    "id": item.get('canal'),
                    "name": item.get('name'),
                    "category": cat_name,
                    "status": res['status'],
                    "latency": res.get('latency', '-'),
                    "code": res.get('code', 0)
                })

        # Guardar resultado para el Dashboard
        with open("status.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)

        print("\n✔ Monitoreo completado. status.json generado.")

    except Exception as e:
        print(f"Fallo crítico: {e}")

if __name__ == "__main__":
    main()
