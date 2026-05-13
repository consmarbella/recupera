"""
Plataforma de Barrido Nacional de Bienes Raices por RUT Chileno
================================================================
Scraping paralelo en:
  1. Conservadores Digitales (conservadoresdigitales.cl) - 80+ comunas
  2. Grandes Conservadores Independientes: Santiago, Vina del Mar, Valparaiso
  3. Portal Fojas (fojas.cl) - conservadores medianos/rurales
  4. Diario Oficial (diariooficial.interior.gob.cl) - sociedades espejo
Consolidacion inteligente con IA
"""

import asyncio
import re
import json
import os
import sys
import subprocess
from typing import Optional
from datetime import datetime

import streamlit as st
from playwright.async_api import async_playwright, TimeoutError as PwTimeout
from openai import OpenAI

# ---------------------------------------------------------------------------
# Instalar Chromium automaticamente si no existe (entorno nube)
# ---------------------------------------------------------------------------
_CHROMIUM_INSTALLED = False


def _ensure_chromium():
    global _CHROMIUM_INSTALLED
    if _CHROMIUM_INSTALLED:
        return
    # Verificar si ya existe el ejecutable de chromium
    home = os.path.expanduser("~")
    possible_paths = [
        os.path.join(home, ".cache", "ms-playwright"),
    ]
    found = False
    for base in possible_paths:
        if os.path.isdir(base):
            for d in os.listdir(base):
                if "chromium" in d.lower():
                    found = True
                    break
    if not found:
        try:
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium", "--with-deps"],
                check=True, capture_output=True, timeout=120
            )
        except Exception:
            try:
                subprocess.run(
                    [sys.executable, "-m", "playwright", "install", "chromium"],
                    check=True, capture_output=True, timeout=120
                )
            except Exception:
                pass
    _CHROMIUM_INSTALLED = True


# ---------------------------------------------------------------------------
# Configuracion global
# ---------------------------------------------------------------------------
NAV_TIMEOUT = 25_000
PAGE_WAIT = 2_000

# Mapa comuna -> region (orden norte-sur)
COMUNA_A_REGION = {
    "Arica": "XV", "Camarones": "XV", "Putre": "XV", "General Lagos": "XV",
    "Iquique": "I", "Alto Hospicio": "I", "Pozo Almonte": "I", "Camina": "I",
    "Colchane": "I", "Huara": "I", "Pica": "I",
    "Antofagasta": "II", "Mejillones": "II", "Sierra Gorda": "II", "Taltal": "II",
    "Calama": "II", "Ollague": "II", "San Pedro de Atacama": "II",
    "Tocopilla": "II", "Maria Elena": "II",
    "Coquimbo": "IV", "Andacollo": "IV", "La Higuera": "IV",
    "Paiguano": "IV", "Vicuna": "IV",
    "Illapel": "IV", "Canela": "IV", "Los Vilos": "IV", "Salamanca": "IV",
    "Ovalle": "IV", "Combarbala": "IV", "Monte Patria": "IV", "Punitaqui": "IV",
    "Rio Hurtado": "IV",
    "Valparaiso": "V", "Vina del Mar": "V", "Concon": "V", "Quintero": "V",
    "Puchuncavi": "V", "Casablanca": "V", "Juan Fernandez": "V",
    "San Antonio": "V", "Cartagena": "V", "El Tabo": "V", "El Quisco": "V",
    "Algarrobo": "V", "Santo Domingo": "V",
    "Quillota": "V", "La Calera": "V", "La Cruz": "V", "Nogales": "V", "Hijuelas": "V",
    "Limache": "V", "Olmue": "V",
    "Villa Alemana": "V", "Quilpue": "V",
    "Los Andes": "V", "San Esteban": "V", "Calle Larga": "V", "Rinconada": "V",
    "San Felipe": "V", "Putaendo": "V", "Santa Maria": "V", "Catemu": "V",
    "Llay-Llay": "V", "Panquehue": "V",
    "Petorca": "V", "La Ligua": "V", "Cabildo": "V", "Zapallar": "V", "Papudo": "V",
    "Isla de Pascua": "V",
    "Santiago": "RM", "Cerrillos": "RM", "Cerro Navia": "RM", "Conchali": "RM",
    "El Bosque": "RM", "Estacion Central": "RM", "Huechuraba": "RM",
    "Independencia": "RM", "La Cisterna": "RM", "La Florida": "RM",
    "La Granja": "RM", "La Pintana": "RM", "La Reina": "RM", "Las Condes": "RM",
    "Lo Barnechea": "RM", "Lo Espejo": "RM", "Lo Prado": "RM", "Macul": "RM",
    "Maipu": "RM", "Nunoa": "RM", "Pedro Aguirre Cerda": "RM", "Penalolen": "RM",
    "Providencia": "RM", "Pudahuel": "RM", "Quilicura": "RM", "Quinta Normal": "RM",
    "Recoleta": "RM", "Renca": "RM", "San Joaquin": "RM", "San Miguel": "RM",
    "San Ramon": "RM", "Vitacura": "RM",
    "Puente Alto": "RM", "Pirque": "RM", "San Jose de Maipo": "RM",
    "Colina": "RM", "Lampa": "RM", "Til Til": "RM",
    "San Bernardo": "RM", "Buin": "RM", "Calera de Tango": "RM", "Paine": "RM",
    "Melipilla": "RM", "Alhue": "RM", "Curacavi": "RM", "Maria Pinto": "RM",
    "San Pedro": "RM",
    "Talagante": "RM", "El Monte": "RM", "Isla de Maipo": "RM", "Padre Hurtado": "RM",
    "Penaflor": "RM",
    "Rancagua": "VI", "Codegua": "VI", "Coinco": "VI", "Coltauco": "VI",
    "Donihue": "VI", "Graneros": "VI", "Las Cabras": "VI", "Machali": "VI",
    "Malloa": "VI", "Mostazal": "VI", "Olivar": "VI", "Peumo": "VI",
    "Pichidegua": "VI", "Quinta de Tilcoco": "VI", "Rengo": "VI", "Requinoa": "VI",
    "San Vicente": "VI", "Pichilemu": "VI", "La Estrella": "VI", "Litueche": "VI",
    "Marchihue": "VI", "Navidad": "VI", "Paredones": "VI",
    "San Fernando": "VI", "Chepica": "VI", "Chimbarongo": "VI", "Lolol": "VI",
    "Nancagua": "VI", "Palmilla": "VI", "Peralillo": "VI", "Placilla": "VI",
    "Pumanque": "VI", "Santa Cruz": "VI",
    "Talca": "VII", "Constitucion": "VII", "Curepto": "VII", "Empedrado": "VII",
    "Maule": "VII", "Pelarco": "VII", "Pencahue": "VII", "Rio Claro": "VII",
    "San Clemente": "VII", "San Rafael": "VII",
    "Cauquenes": "VII", "Chanco": "VII", "Pelluhue": "VII",
    "Curico": "VII", "Hualane": "VII", "Licanten": "VII", "Molina": "VII",
    "Rauco": "VII", "Romeral": "VII", "Sagrada Familia": "VII", "Teno": "VII",
    "Vichuquen": "VII",
    "Linares": "VII", "Colbun": "VII", "Longavi": "VII", "Parral": "VII",
    "Retiro": "VII", "San Javier": "VII", "Villa Alegre": "VII", "Yerbas Buenas": "VII",
    "Chillan": "XVI", "Chillan Viejo": "XVI", "Bulnes": "XVI", "Cobquecura": "XVI",
    "Coelemu": "XVI", "Coihueco": "XVI", "El Carmen": "XVI", "Ninhue": "XVI",
    "Niquen": "XVI", "Pemuco": "XVI", "Pinto": "XVI", "Portezuelo": "XVI",
    "Quillon": "XVI", "Quirihue": "XVI", "Ranquil": "XVI", "San Carlos": "XVI",
    "San Fabian": "XVI", "San Ignacio": "XVI", "San Nicolas": "XVI", "Treguaco": "XVI",
    "Yungay": "XVI",
    "Concepcion": "VIII", "Coronel": "VIII", "Chiguayante": "VIII", "Florida": "VIII",
    "Hualqui": "VIII", "Lota": "VIII", "Penco": "VIII", "San Pedro de la Paz": "VIII",
    "Santa Juana": "VIII", "Talcahuano": "VIII", "Tome": "VIII", "Hualpen": "VIII",
    "Lebu": "VIII", "Arauco": "VIII", "Canete": "VIII", "Contulmo": "VIII",
    "Curanilahue": "VIII", "Los Alamos": "VIII", "Tirua": "VIII",
    "Los Angeles": "VIII", "Antuco": "VIII", "Cabrero": "VIII", "Laja": "VIII",
    "Mulchen": "VIII", "Nacimiento": "VIII", "Negrete": "VIII", "Quilaco": "VIII",
    "Quilleco": "VIII", "San Rosendo": "VIII", "Santa Barbara": "VIII",
    "Tucapel": "VIII", "Yumbel": "VIII", "Alto Biobio": "VIII",
    "Temuco": "IX", "Carahue": "IX", "Cholchol": "IX", "Cunco": "IX",
    "Curarrehue": "IX", "Freire": "IX", "Galvarino": "IX", "Gorbea": "IX",
    "Lautaro": "IX", "Loncoche": "IX", "Melipeuco": "IX", "Nueva Imperial": "IX",
    "Padre Las Casas": "IX", "Perquenco": "IX", "Pitrufquen": "IX", "Pucon": "IX",
    "Saavedra": "IX", "Teodoro Schmidt": "IX", "Tolten": "IX", "Vilcun": "IX",
    "Villarrica": "IX",
    "Angol": "IX", "Collipulli": "IX", "Curacautin": "IX", "Ercilla": "IX",
    "Lonquimay": "IX", "Los Sauces": "IX", "Lumaco": "IX", "Puren": "IX",
    "Renaico": "IX", "Traiguen": "IX", "Victoria": "IX",
    "Valdivia": "XIV", "Corral": "XIV", "Lanco": "XIV", "Los Lagos": "XIV",
    "Mafil": "XIV", "Mariquina": "XIV", "Paillaco": "XIV", "Panguipulli": "XIV",
    "La Union": "XIV", "Futrono": "XIV", "Lago Ranco": "XIV", "Rio Bueno": "XIV",
    "Osorno": "X", "Puerto Octay": "X", "Purranque": "X", "Puyehue": "X",
    "Rio Negro": "X", "San Juan de la Costa": "X", "San Pablo": "X",
    "Puerto Montt": "X", "Calbuco": "X", "Cochamo": "X", "Fresia": "X",
    "Frutillar": "X", "Los Muermos": "X", "Llanquihue": "X", "Maullin": "X",
    "Puerto Varas": "X",
    "Castro": "X", "Ancud": "X", "Chonchi": "X", "Curaco de Velez": "X",
    "Dalcahue": "X", "Puqueldon": "X", "Queilen": "X", "Quellon": "X",
    "Quemchi": "X", "Quinchao": "X",
    "Chaiten": "X", "Futaleufu": "X", "Hualaihue": "X", "Palena": "X",
    "Coyhaique": "XI", "Lago Verde": "XI", "Aysen": "XI", "Cisnes": "XI",
    "Guaitecas": "XI", "Chile Chico": "XI", "Rio Ibanez": "XI",
    "Cochrane": "XI", "O'Higgins": "XI", "Tortel": "XI",
    "Punta Arenas": "XII", "Laguna Blanca": "XII", "Rio Verde": "XII",
    "San Gregorio": "XII", "Porvenir": "XII", "Primavera": "XII", "Timaukel": "XII",
    "Natales": "XII", "Torres del Paine": "XII",
    "Cabo de Hornos": "XII", "Antartica": "XII",
}

ORDEN_REGION = {
    "XV": 1, "I": 2, "II": 3, "III": 4, "IV": 5,
    "V": 6, "RM": 7, "VI": 8, "VII": 9, "XVI": 10,
    "VIII": 11, "IX": 12, "XIV": 13, "X": 14, "XI": 15, "XII": 16,
}

# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def normalizar_rut(rut: str) -> str:
    return rut.upper().replace(".", "").replace("-", "").strip()


def extraer_options_select(html: str) -> list[str]:
    patron = r'<option[^>]*value=["\']([^"\']*)["\'][^>]*>([^<]+)</option>'
    matches = re.findall(patron, html, re.IGNORECASE)
    opciones = []
    for value, texto in matches:
        t = texto.strip()
        if t and value and value != "0" and t.lower() not in ("seleccione", "", "todos"):
            opciones.append(t)
    return opciones


async def buscar_input_rut(page, rut: str) -> bool:
    selectores = [
        "input[name*='rut' i]", "input[id*='rut' i]",
        "input[placeholder*='rut' i]", "input#TxtRut",
        "input#rut", "input#Rut",
    ]
    for sel in selectores:
        inp = await page.query_selector(sel)
        if inp:
            await inp.fill("")
            await inp.fill(rut)
            return True
    inputs = await page.query_selector_all("input[type='text'], input:not([type])")
    for inp in inputs:
        ph = (await inp.get_attribute("placeholder") or "").lower()
        nm = (await inp.get_attribute("name") or "").lower()
        if "rut" in ph or "rut" in nm:
            await inp.fill("")
            await inp.fill(rut)
            return True
    return False


async def click_boton_consultar(page) -> bool:
    selectores = [
        "button[type='submit']", "input[type='submit']",
        "button:has-text('Consultar')", "button:has-text('Buscar')",
        "a:has-text('Consultar')", "input[value*='Consultar' i]",
        "input[value*='Buscar' i]", "button:has-text('Filtrar')",
    ]
    for sel in selectores:
        btn = await page.query_selector(sel)
        if btn:
            await btn.click()
            return True
    return False


# ===================================================================
# MODULO 1: Conservadores Digitales (conservadoresdigitales.cl)
# ===================================================================
async def extraer_comunas_cd(page) -> list[str]:
    await page.goto("https://www.conservadoresdigitales.cl",
                    timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    for sel in ["select#CmbComuna", "select[name*='comuna' i]", "select[id*='comuna' i]"]:
        el = await page.query_selector(sel)
        if el:
            html = await el.inner_html()
            opts = extraer_options_select(f"<select>{html}</select>")
            if opts:
                return opts
    html = await page.content()
    return extraer_options_select(html)


async def consultar_cd_comuna(page, rut: str, comuna: str) -> dict:
    res = {"fuente": "conservadoresdigitales", "comuna": comuna,
           "raw_html": "", "encontrado": False, "error": None}
    try:
        await page.goto("https://www.conservadoresdigitales.cl",
                        timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        for sel in ["select#CmbComuna", "select[name*='comuna' i]", "select[id*='comuna' i]", "select"]:
            el = await page.query_selector(sel)
            if el:
                try:
                    await el.select_option(label=comuna)
                    await page.wait_for_timeout(800)
                    break
                except Exception:
                    continue
        await buscar_input_rut(page, rut)
        await page.wait_for_timeout(500)
        ok = await click_boton_consultar(page)
        if not ok:
            await page.keyboard.press("Enter")
        await page.wait_for_timeout(3000)
        html = await page.content()
        res["raw_html"] = html
        txt = html.lower()
        if "no se encontraron" not in txt and "sin resultados" not in txt:
            if ("<table" in html or "resultado" in txt) and \
               any(w in html for w in ["Foja", "Fojas", "Inscripcion"]):
                res["encontrado"] = True
    except Exception as e:
        res["error"] = str(e)
    return res


async def barrido_conservadores_digitales(rut: str, max_par: int = 5) -> list[dict]:
    resultados = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await ctx.new_page()
        st.info("Extrayendo comunas disponibles...")
        comunas = await extraer_comunas_cd(page)
        if not comunas:
            st.warning("Usando lista de respaldo de comunas.")
            comunas = list(COMUNA_A_REGION.keys())
        st.info(f"{len(comunas)} comunas detectadas. Barriendo en paralelo...")
        await page.close()
        await ctx.close()
        sem = asyncio.Semaphore(max_par)

        async def tarea(comuna):
            async with sem:
                c = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                p = await c.new_page()
                try:
                    return await consultar_cd_comuna(p, rut, comuna)
                finally:
                    await p.close()
                    await c.close()

        resultados = await asyncio.gather(*[tarea(c) for c in comunas])
        await browser.close()
    return resultados


# ===================================================================
# MODULO 2: Grandes Conservadores Independientes
# ===================================================================
CONSERVADORES_INDEP = [
    ("Santiago",     "https://www.cbrsantiago.cl"),
    ("Vina del Mar", "https://www.cbrvina.cl"),
    ("Valparaiso",   "https://www.cbrvalparaiso.cl"),
]


async def consultar_independiente(page, url: str, rut: str, nombre: str) -> dict:
    res = {"fuente": "independiente", "conservador": nombre,
           "raw_html": "", "encontrado": False, "error": None}
    try:
        await page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        await buscar_input_rut(page, rut)
        await page.wait_for_timeout(500)
        ok = await click_boton_consultar(page)
        if not ok:
            await page.keyboard.press("Enter")
        await page.wait_for_timeout(3000)
        html = await page.content()
        res["raw_html"] = html
        txt = html.lower()
        if "no se encontraron" not in txt and "sin resultados" not in txt:
            if "<table" in html or any(w in html for w in ["Foja", "Fojas", "Inscripcion"]):
                res["encontrado"] = True
    except Exception as e:
        res["error"] = str(e)
    return res


async def barrido_independientes(rut: str) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        async def tarea(nombre, url):
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            pg = await ctx.new_page()
            try:
                return await consultar_independiente(pg, url, rut, nombre)
            finally:
                await pg.close()
                await ctx.close()

        st.info("Consultando Conservadores Regionales...")
        resultados = await asyncio.gather(*[tarea(n, u) for n, u in CONSERVADORES_INDEP])
        await browser.close()
        return resultados


# ===================================================================
# MODULO 3: Portal Fojas (fojas.cl)
# ===================================================================
async def consultar_fojas(page, rut: str) -> dict:
    res = {"fuente": "fojas", "conservador": "general",
           "raw_html": "", "encontrado": False, "error": None}
    try:
        await page.goto("https://www.fojas.cl",
                        timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        await buscar_input_rut(page, rut)
        await page.wait_for_timeout(500)
        ok = await click_boton_consultar(page)
        if not ok:
            await page.keyboard.press("Enter")
        await page.wait_for_timeout(3000)
        html = await page.content()
        res["raw_html"] = html
        txt = html.lower()
        if "no se encontraron" not in txt and "sin resultados" not in txt:
            if "<table" in html or "resultado" in txt:
                res["encontrado"] = True
    except Exception as e:
        res["error"] = str(e)
    return res


async def barrido_fojas(rut: str) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await ctx.new_page()
        st.info("Consultando registros nacionales...")
        res = await consultar_fojas(page, rut)
        await page.close()
        await ctx.close()
        await browser.close()
        return [res]


# ===================================================================
# MODULO 4: Diario Oficial (diariooficial.interior.gob.cl)
# ===================================================================
async def buscar_diario_oficial(page, rut: str) -> dict:
    res = {"fuente": "diario_oficial", "conservador": "nacional",
           "raw_html": "", "encontrado": False, "error": None}
    try:
        url = "https://www.diariooficial.interior.gob.cl"
        await page.goto(url, timeout=NAV_TIMEOUT, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        input_busqueda = None
        selectores = [
            "input[name*='buscar' i]", "input[name*='search' i]",
            "input[id*='buscar' i]", "input[id*='search' i]",
            "input[placeholder*='buscar' i]", "input[placeholder*='search' i]",
            "input[type='text']",
        ]
        for sel in selectores:
            inp = await page.query_selector(sel)
            if inp:
                input_busqueda = inp
                break
        if input_busqueda:
            await input_busqueda.fill("")
            await input_busqueda.fill(rut)
            await page.wait_for_timeout(500)
            ok = await click_boton_consultar(page)
            if not ok:
                for txt in ["Buscar", "Search", "Ir", "Filtrar"]:
                    btn = await page.query_selector(f"button:has-text('{txt}')")
                    if btn:
                        await btn.click()
                        break
                else:
                    await page.keyboard.press("Enter")
            await page.wait_for_timeout(3000)
        html = await page.content()
        res["raw_html"] = html
        txt = html.lower()
        if "no se encontraron" not in txt and "sin resultados" not in txt:
            palabras_clave = ["sociedad", "extracto", "constitucion",
                              "publicacion", "diario oficial", rut.lower()]
            if any(p in txt for p in palabras_clave):
                res["encontrado"] = True
    except Exception as e:
        res["error"] = str(e)
    return res


async def barrido_diario_oficial(rut: str) -> list[dict]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await ctx.new_page()
        st.info("Buscando publicaciones oficiales...")
        res = await buscar_diario_oficial(page, rut)
        await page.close()
        await ctx.close()
        await browser.close()
        return [res]


# ===================================================================
# MODULO 5: Consolidacion Inteligente
# ===================================================================
def consolidar_con_ia(client: OpenAI, raw_data: list[dict], rut: str) -> str:
    bloque_html = []
    for item in raw_data:
        fuente = item.get("fuente", "desconocida")
        comuna = item.get("comuna", item.get("conservador", "general"))
        encontrado = item.get("encontrado", False)
        html = item.get("raw_html", "")[:5000]
        error = item.get("error")
        bloque_html.append(
            f"--- Fuente: {fuente} | Ubicacion: {comuna} | "
            f"Hallazgo: {encontrado} | Error: {error or 'N/A'} ---\n"
            f"{html}\n"
        )
    texto_completo = "\n\n".join(bloque_html)

    system_prompt = """Eres un asistente experto en analisis de inscripciones de bienes raices y sociedades en Chile.

Tu tarea es analizar los resultados HTML de busquedas en Conservadores de Bienes Raices y el Diario Oficial.

Debes:
1. Identificar TODAS las inscripciones vigentes encontradas para el RUT consultado en los Conservadores de Bienes Raices.
2. Extraer para cada inscripcion: Comuna, Foja, Numero, Anio, y cualquier detalle adicional relevante.
3. Identificar si el RUT aparece en el Diario Oficial como socio o representante de sociedades.
4. Eliminar duplicados (misma Foja+Numero+Anio en misma comuna).
5. Ignorar paginas sin resultados o con errores.
6. Ordenar los resultados de norte a sur de Chile.

Responde UNICAMENTE con un JSON valido con esta estructura:
{
  "resumen": "Breve resumen de todos los hallazgos",
  "total_inscripciones": 0,
  "total_sociedades": 0,
  "inscripciones": [
    {
      "comuna": "Nombre Comuna",
      "region": "RM",
      "foja": "123",
      "numero": "456",
      "anio": "2024",
      "detalle": "Texto adicional relevante",
      "fuente": "conservadoresdigitales / fojas / independiente"
    }
  ],
  "sociedades": [
    {
      "tipo": "Sociedad / Extracto",
      "rut_sociedad": "76.123.456-7",
      "nombre_sociedad": "Nombre de la sociedad si se encuentra",
      "fecha_publicacion": "2024-01-15",
      "detalle": "Texto del extracto",
      "fuente": "diario_oficial"
    }
  ]
}

Si NO se encontraron inscripciones ni sociedades, responde:
{"resumen": "No se encontraron inscripciones vigentes ni sociedades para el RUT consultado.", "total_inscripciones": 0, "total_sociedades": 0, "inscripciones": [], "sociedades": []}
"""

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"RUT consultado: {rut}\n\nDatos crudos de busqueda:\n\n{texto_completo[:120000]}"}
            ],
            temperature=0.1,
            max_tokens=4000,
        )
        return response.choices[0].message.content
    except Exception as e:
        return json.dumps({
            "resumen": f"Error al procesar con IA: {str(e)}",
            "total_inscripciones": 0,
            "total_sociedades": 0,
            "inscripciones": [],
            "sociedades": []
        })


# ===================================================================
# INTERFAZ STREAMLIT
# ===================================================================
def main():
    # Instalar Chromium si es necesario (entorno nube)
    _ensure_chromium()

    st.set_page_config(
        page_title="Barrido Nacional de Bienes Raices",
        page_icon="house",
        layout="wide",
    )

    st.title("Barrido Nacional de Bienes Raices por RUT")
    st.markdown("""
    Consulta simultanea en **+80 Conservadores de Bienes Raices** de Chile:
    - Red Nacional de Conservadores Digitales
    - Grandes Conservadores Regionales
    - Registros Nacionales Centralizados
    - Publicaciones Oficiales
    """)

    with st.sidebar:
        st.header("Configuracion")

        rut_input = st.text_input(
            "RUT del deudor",
            placeholder="12.345.678-5",
            help="RUT con o sin puntos y guion"
        )

        max_par = st.slider(
            "Consultas paralelas",
            min_value=1, max_value=15, value=5,
            help="Maximo de consultas simultaneas"
        )

        incluir_digitales = st.checkbox("Red Nacional de Conservadores", value=True)
        incluir_independientes = st.checkbox("Grandes Conservadores Regionales", value=True)
        incluir_fojas = st.checkbox("Registros Nacionales", value=True)
        incluir_diario = st.checkbox("Publicaciones Oficiales", value=True)

        ejecutar = st.button("Iniciar Barrido Nacional", type="primary", use_container_width=True)

    if ejecutar:
        # Leer API Key solo desde Secrets (nunca desde input del usuario)
        api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            st.error("Error de configuracion del sistema. Contacte al administrador.")
            return
        if not rut_input:
            st.error("Debes ingresar un RUT.")
            return

        rut = normalizar_rut(rut_input)
        if len(rut) < 8 or not rut[:-1].isdigit():
            st.error("RUT invalido. Ej: 12345678-5")
            return

        # Cliente OpenAI apuntando a DeepSeek
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com"
        )

        log_container = st.container()
        progress_bar = st.progress(0, text="Iniciando barrido nacional...")

        all_results = []
        modulos_activos = sum([incluir_digitales, incluir_independientes,
                               incluir_fojas, incluir_diario])
        modulos_ok = 0

        # --- MODULO 1: Conservadores Digitales ---
        if incluir_digitales:
            with log_container:
                st.subheader("Red Nacional de Conservadores")
            progress_bar.progress(int(modulos_ok / modulos_activos * 100),
                                  text="Barriendo comunas en paralelo...")
            try:
                r = asyncio.run(barrido_conservadores_digitales(rut, max_par))
                all_results.extend(r)
                enc = sum(1 for x in r if x.get("encontrado"))
                with log_container:
                    st.success(f"{enc} comunas con hallazgos.")
            except Exception as e:
                with log_container:
                    st.error(f"Error: {e}")
            modulos_ok += 1

        # --- MODULO 2: Independientes ---
        if incluir_independientes:
            with log_container:
                st.subheader("Grandes Conservadores Regionales")
            progress_bar.progress(int(modulos_ok / modulos_activos * 100),
                                  text="Consultando Santiago, Vina, Valparaiso...")
            try:
                r = asyncio.run(barrido_independientes(rut))
                all_results.extend(r)
                enc = sum(1 for x in r if x.get("encontrado"))
                with log_container:
                    st.success(f"{enc} con hallazgos.")
            except Exception as e:
                with log_container:
                    st.error(f"Error: {e}")
            modulos_ok += 1

        # --- MODULO 3: Portal Fojas ---
        if incluir_fojas:
            with log_container:
                st.subheader("Registros Nacionales")
            progress_bar.progress(int(modulos_ok / modulos_activos * 100),
                                  text="Consultando registros...")
            try:
                r = asyncio.run(barrido_fojas(rut))
                all_results.extend(r)
                enc = sum(1 for x in r if x.get("encontrado"))
                with log_container:
                    st.success(f"{'Hallazgos' if enc else 'Sin resultados'}.")
            except Exception as e:
                with log_container:
                    st.error(f"Error: {e}")
            modulos_ok += 1

        # --- MODULO 4: Diario Oficial ---
        if incluir_diario:
            with log_container:
                st.subheader("Publicaciones Oficiales")
            progress_bar.progress(int(modulos_ok / modulos_activos * 100),
                                  text="Buscando publicaciones...")
            try:
                r = asyncio.run(barrido_diario_oficial(rut))
                all_results.extend(r)
                enc = sum(1 for x in r if x.get("encontrado"))
                with log_container:
                    st.success(f"{'Publicaciones encontradas' if enc else 'Sin resultados'}.")
            except Exception as e:
                with log_container:
                    st.error(f"Error: {e}")
            modulos_ok += 1

        # --- MODULO 5: Consolidacion IA ---
        progress_bar.progress(90, text="Analizando resultados...")
        with log_container:
            st.subheader("Analisis Inteligente")

        with st.spinner("Procesando y estructurando resultados..."):
            respuesta_ia = consolidar_con_ia(client, all_results, rut)

        progress_bar.progress(100, text="Barrido completado!")

        # --- RESULTADOS ---
        st.markdown("---")
        st.header("Resultados del Barrido Nacional")

        try:
            datos = json.loads(respuesta_ia)
        except json.JSONDecodeError:
            st.error("Error al procesar resultados. Mostrando crudo:")
            st.text(respuesta_ia)
            return

        st.subheader("Resumen")
        st.info(datos.get("resumen", "Sin resumen."))

        total_insc = datos.get("total_inscripciones", 0)
        total_soc = datos.get("total_sociedades", 0)
        inscripciones = datos.get("inscripciones", [])
        sociedades = datos.get("sociedades", [])

        col_a, col_b, col_c, col_d = st.columns(4)
        with col_a:
            st.metric("Total Inscripciones", total_insc)
        with col_b:
            st.metric("Sociedades", total_soc)
        with col_c:
            st.metric("Comunas", len(set(i.get("comuna", "") for i in inscripciones)))
        with col_d:
            st.metric("Regiones", len(set(i.get("region", "") for i in inscripciones)))

        # Tabla de inscripciones
        if inscripciones:
            st.subheader("Inscripciones de Bienes Raices (Norte a Sur)")
            ins_ord = sorted(
                inscripciones,
                key=lambda x: (ORDEN_REGION.get(x.get("region", "ZZ"), 99), x.get("comuna", ""))
            )
            tbl = []
            for idx, ins in enumerate(ins_ord, 1):
                tbl.append({
                    "#": idx,
                    "Comuna": ins.get("comuna", ""),
                    "Region": ins.get("region", ""),
                    "Foja": ins.get("foja", ""),
                    "Numero": ins.get("numero", ""),
                    "Anio": ins.get("anio", ""),
                    "Fuente": ins.get("fuente", ""),
                })
            st.dataframe(tbl, use_container_width=True, hide_index=True)

            with st.expander("Ver detalle completo de inscripciones"):
                for ins in ins_ord:
                    st.markdown(f"""
**{ins.get('comuna', 'N/A')}** ({ins.get('region', 'N/A')})
- Foja: {ins.get('foja', 'N/A')} | Numero: {ins.get('numero', 'N/A')} | Anio: {ins.get('anio', 'N/A')}
- Fuente: {ins.get('fuente', 'N/A')}
- Detalle: {ins.get('detalle', 'Sin detalle')}
---
""")

        # Tabla de sociedades
        if sociedades:
            st.subheader("Sociedades encontradas")
            tbl_soc = []
            for idx, soc in enumerate(sociedades, 1):
                tbl_soc.append({
                    "#": idx,
                    "Tipo": soc.get("tipo", ""),
                    "RUT Sociedad": soc.get("rut_sociedad", ""),
                    "Nombre": soc.get("nombre_sociedad", ""),
                    "Fecha": soc.get("fecha_publicacion", ""),
                    "Fuente": soc.get("fuente", ""),
                })
            st.dataframe(tbl_soc, use_container_width=True, hide_index=True)

            with st.expander("Ver detalle de sociedades"):
                for soc in sociedades:
                    st.markdown(f"""
**{soc.get('nombre_sociedad', 'N/A')}** (RUT: {soc.get('rut_sociedad', 'N/A')})
- Tipo: {soc.get('tipo', 'N/A')}
- Fecha publicacion: {soc.get('fecha_publicacion', 'N/A')}
- Detalle: {soc.get('detalle', 'Sin detalle')}
---
""")

        if not inscripciones and not sociedades:
            st.warning("No se encontraron inscripciones ni sociedades para el RUT consultado.")

        # Descargar JSON
        st.download_button(
            label="Descargar resultados (JSON)",
            data=respuesta_ia,
            file_name=f"resultados_rut_{rut}.json",
            mime="application/json",
        )


if __name__ == "__main__":
    main()
