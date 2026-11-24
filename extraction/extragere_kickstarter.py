import json
import os
import random
import re
import time
from datetime import datetime, timezone

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

STUDIO_KEYWORDS = [
    "studio", "studios", "games", "gaming", "interactive",
    "entertainment", "soft", "software", "dev", "labs", "team", "inc", "llc"
]


def contine_cuvinte(text, cuvinte):
    text = text.lower()
    return int(any(re.search(rf"\b{re.escape(c)}\b", text) for c in cuvinte))


def salveaza_csv(proiecte, cale_fisier):
    if not proiecte:
        return None
    df = pd.DataFrame(proiecte).drop_duplicates(subset=["id_proiect"]).reset_index(drop=True)
    os.makedirs(os.path.dirname(cale_fisier), exist_ok=True)
    df.to_csv(cale_fisier, index=False, encoding="utf-8-sig")
    return df


def porneste_driver():
    # configurare chrome fara flag-ul de automatizare pentru a evita 403
    opts = Options()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def parseaza_proiect(p, stare):
    launched = float(p.get("launched_at") or 0)
    deadline = float(p.get("deadline") or 0)
    created = float(p.get("created_at") or 0)

    durata_zile = (deadline - launched) / 86400 if launched else 0
    zile_pregatire = (launched - created) / 86400 if created else 0
    data_lansare = datetime.fromtimestamp(launched, tz=timezone.utc) if launched else datetime.now(timezone.utc)

    titlu = str(p.get("name") or "")
    descriere = str(p.get("blurb") or "")
    text = f"{titlu} {descriere}"

    goal = float(p.get("goal") or 0)
    rata_usd = float(p.get("static_usd_rate") or 1.0)
    creator = p.get("creator") or {}
    loc = p.get("location") or {}
    cat = p.get("category") or {}
    tara = str(p.get("country") or "Unknown")

    return {
        "id_proiect": p.get("id"),
        "nume_proiect": titlu,
        "categorie": cat.get("name", "Video Games"),
        "stare_text": stare,
        "target_status": 1 if stare == "successful" else 0,
        "are_video": int(bool(p.get("video"))),
        "usd_type": str(p.get("usd_type", "unknown")),
        "locatie_stat": str(loc.get("state", "Unknown")),
        "creator_is_superbacker": int(bool(creator.get("is_superbacker"))),
        "obiectiv_usd": round(goal * rata_usd, 2),
        "obiectiv_original": round(goal, 2),
        "moneda": str(p.get("currency", "USD")),
        "obiectiv_rotund_1000": int(goal > 0 and goal % 1000 == 0),
        "durata_campanie_zile": round(durata_zile, 1),
        "zile_pregatire": round(zile_pregatire, 1),
        "anul_lansarii": data_lansare.year,
        "luna_lansarii": data_lansare.month,
        "trimestrul_lansarii": (data_lansare.month - 1) // 3 + 1,
        "ziua_saptamanii": data_lansare.weekday(),
        "ora_lansarii_utc": data_lansare.hour,
        "este_weekend_lansare": int(data_lansare.weekday() >= 5),
        "prelaunch_activated": int(bool(p.get("prelaunch_activated"))),
        "este_staff_pick": int(bool(p.get("staff_pick"))),
        "tara": tara,
        "este_sua": int(tara.upper() == "US"),
        "tip_locatie": str(loc.get("type", "Unknown")),
        "creator_id": creator.get("id"),
        "creator_pare_studio": contine_cuvinte(str(creator.get("name") or ""), STUDIO_KEYWORDS),
        "titlu_nr_caractere": len(titlu),
        "titlu_nr_cuvinte": len(titlu.split()),
        "titlu_are_subtitlu": int(":" in titlu or " - " in titlu),
        "descriere_nr_caractere": len(descriere),
        "descriere_nr_cuvinte": len(descriere.split()),
        "descriere_are_exclamare": int("!" in descriere),
        "mentioneaza_demo": contine_cuvinte(text, ["demo", "prototype", "playtest", "playable"]),
        "mentioneaza_pc_steam": contine_cuvinte(text, ["steam", "pc", "windows", "mac", "linux"]),
        "mentioneaza_console": contine_cuvinte(text, ["switch", "nintendo", "ps4", "ps5", "playstation", "xbox", "console"]),
        "mentioneaza_rpg": contine_cuvinte(text, ["rpg", "jrpg", "mmorpg", "action-rpg", "arpg"]),
        "mentioneaza_retro_pixel": contine_cuvinte(text, ["pixel", "retro", "2d", "8-bit", "16-bit", "pixelart"]),
        "mentioneaza_multiplayer": contine_cuvinte(text, ["multiplayer", "co-op", "coop", "online", "pvp", "mmo"]),
        "mentioneaza_vr": contine_cuvinte(text, ["vr", "virtual reality", "oculus", "quest"]),
        "LEAK_suma_obtinuta_usd": round(float(p.get("pledged") or 0) * rata_usd, 2),
        "LEAK_numar_donatori": int(p.get("backers_count") or 0),
        "LEAK_procent_finantare": round(float(p.get("percent_funded") or 0), 2),
        "url_proiect": p.get("urls", {}).get("web", {}).get("project", ""),
    }


def extrage_video_games(pagini_per_stare=105):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cale_csv = os.path.join(base_dir, "..", "data", "dataset_kickstarter_video_games.csv")

    driver = porneste_driver()
    proiecte = []

    try:
        for stare in ["successful", "failed"]:
            print(f"Extragem: {stare}")
            for pagina in range(1, pagini_per_stare + 1):
                url = (
                    "https://www.kickstarter.com/discover/advanced"
                    f"?format=json&category_id=35&state={stare}&page={pagina}&sort=end_date"
                )
                try:
                    driver.get(url)
                    date = json.loads(driver.execute_script("return document.body.innerText;"))
                    lista = date.get("projects", [])
                    if not lista:
                        break

                    adaugate = 0
                    for p in lista:
                        # pastram doar proiectele din subcategoria Video Games (id 35)
                        cat = p.get("category") or {}
                        if cat.get("id") != 35 and "video games" not in str(cat.get("slug", "")).lower():
                            continue
                        if p.get("state") != stare:
                            continue

                        proiecte.append(parseaza_proiect(p, stare))
                        adaugate += 1

                    print(f"[{stare}] pag {pagina}/{pagini_per_stare}: +{adaugate} (total {len(proiecte)})")

                    # checkpoint la fiecare 20 de pagini
                    if pagina % 20 == 0:
                        salveaza_csv(proiecte, cale_csv)

                    # pauza aleatorie pentru rate limit
                    time.sleep(random.uniform(2.5, 5.0))
                except Exception as err:
                    print(f"Eroare [{stare}] pag {pagina}: {err}")
                    time.sleep(10)
    finally:
        driver.quit()
        df = salveaza_csv(proiecte, cale_csv)
        if df is not None:
            print(f"Gata: {len(df)} proiecte salvate in {os.path.abspath(cale_csv)}")
            print(df["stare_text"].value_counts().to_dict())


if __name__ == "__main__":
    extrage_video_games(pagini_per_stare=105)