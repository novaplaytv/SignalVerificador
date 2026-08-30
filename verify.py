import os
import json
import requests
import time
import urllib3

# Silenciar advertencias de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def get_flow_token():
    try:
        token_api = os.getenv("TOKEN_API_URL")
        if not token_api: return None
        res = requests.get(token_api, timeout=10, verify=False)
        if res.status_code == 200:
            data = res.json()
            return data.get("token") or data.get("value", {}).get("token")
    except: return None
    return None

def check_signal(name, url, headers, is_flow=False, token=None):
    try:
        test_url = url
        test_headers = headers.copy()
        if is_flow and token:
            test_url = url.replace("[TOKEN]", token).replace("TOKEN_AQUÍ", token)
            if "tok_" not in test_url and "token=" not in test_url:
                separator = "&" if "?" in test_url else "?"
                test_url += f"{separator}token={token}"

        start_time = time.time()
        response = requests.get(test_url, headers=test_headers, timeout=30, stream=True, verify=False)
        elapsed = time.time() - start_time

        content_peek = response.raw.read(2048).decode('utf-8', errors='ignore').upper()
        is_m3u8 = "#EXTM3U" in content_peek
        is_mpd = "<MPD" in content_peek or "DASH+XML" in response.headers.get("Content-Type", "").upper()

        if response.status_code in [200, 206] and (is_m3u8 or is_mpd):
            return {"status": "ONLINE", "latency": f"{int(elapsed*1000)}ms", "code": response.status_code}
        elif response.status_code in [301, 302, 307, 308]:
            return {"status": "REDIRECT", "latency": f"{int(elapsed*1000)}ms", "code": response.status_code}
        else:
            status = "OFFLINE"
            if response.status_code == 403 and is_flow: status = "PROTECTED"
            return {"status": status, "code": response.status_code}

    except Exception as e:
        return {"status": "ERROR", "msg": str(e)[:50]}

def main():
    source_url = os.getenv("JSON_SOURCE_URL")
    if not source_url: return

    # 1. Cargar Overrides Manuales
    overrides = {}
    if os.path.exists("manual_overrides.json"):
        try:
            with open("manual_overrides.json", "r", encoding="utf-8") as f:
                overrides = json.load(f)
        except Exception as e:
            print(f"Error cargando manual_overrides.json: {e}")

    # 2. Cargar status.json previo para no borrarlo si falla algo
    old_report = {"last_update": "N/A", "results": []}
    if os.path.exists("status.json"):
        try:
            with open("status.json", "r", encoding="utf-8") as f:
                old_report = json.load(f)
        except: pass

    flow_token = get_flow_token()

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
                canal_id = str(item.get('canal'))
                if not url: continue

                # --- PRIORIDAD MANUAL ---
                if canal_id in overrides and overrides[canal_id].get("manual_online") is True:
                    report["results"].append({
                        "id": canal_id,
                        "name": item.get('name'),
                        "category": cat_name,
                        "status": "MANUAL_ONLINE",
                        "latency": "Verificado Manualmente",
                        "code": 200
                    })
                    print(f"[{cat_name}] {item.get('name')}... MANUAL ONLINE")
                    continue

                is_flow = item.get('flow') == "yes" or "flow" in url.lower()
                headers = {
                    "User-Agent": item.get('User-Agent', "PlayTVPremium"),
                    "Origin": item.get('Origin', "https://portal.app.flow.com.ar"),
                    "Referer": item.get('Referer', "https://portal.app.flow.com.ar/")
                }

                res = check_signal(item.get('name'), url, headers, is_flow, flow_token)
                print(f"[{cat_name}] {item.get('name')}... {res['status']} ({res.get('code', 'ERR')})")

                report["results"].append({
                    "id": canal_id,
                    "name": item.get('name'),
                    "category": cat_name,
                    "status": res['status'],
                    "latency": res.get('latency', '-'),
                    "code": res.get('code', 0)
                })

        with open("status.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4)
        print("\n✔ Verificaciín completada con íxito.")

    except Exception as e:
        print(f"Fallo crético en escaneo: {e}. Preservando reporte anterior.")
        with open("status.json", "w", encoding="utf-8") as f:
            json.dump(old_report, f, indent=4)

if __name__ == "__main__":
    main()
