"""Parámetros editables compartidos entre hojas y sus versiones.

Una versión reúne todo lo editable: parámetros RIE, decisión por rama del Árbol y mitigantes
exigidos en Mitigantes, porque dependen entre sí (el RIE define las ramas que reciben decisión).

- Al iniciar la sesión se carga la versión 1 (config/versiones/base_v1.json), que no se modifica.
- Lo editado vive en st.session_state con claves propias (no las de los widgets, que Streamlit
  borra al cambiar de hoja), así que se aplica en todas las hojas durante la sesión.
- «Guardar como nueva versión» crea config/versiones/<usuario>_v<N>.json; nunca sobrescribe otro
  archivo, de modo que varios usuarios pueden guardar a la vez sin pisarse.
- Cada usuario solo elimina sus propias versiones; la versión 1 no se elimina.
"""
import copy
import json
import os
import re
import tempfile
import unicodedata
from datetime import datetime

import streamlit as st

from src.data_loader import ROOT
from src.rie import DEFAULT_PARAMS

VERSIONS_DIR = ROOT / "config" / "versiones"
BASE_VERSION = "base_v1"
APROBADO, CONDICIONES, A_ESTUDIO = "Aprobado", "Condiciones", "A estudio"
DECISION_OPTIONS = [APROBADO, CONDICIONES, A_ESTUDIO]

RIE_STATE = "rie_parametros"
ARBOL_DECISION_STATE = "arbol_decisiones"
CONDICIONES_STATE = "mitigantes_condiciones"
ACTIVE_STATE = "version_activa"
USER_STATE = "version_usuario"
MESSAGE_STATE = "version_mensaje"
SELECT_STATE = "version_seleccion"
# Editores que se reconstruyen desde los parámetros al cargar o descartar una versión.
EDITOR_PREFIXES = ("rie_editor_", "rie_input_", "arbol_tabla_editor_", "mit_condiciones_editor_")

def read_json(path):
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            st.warning(f"No se pudo leer `{path.relative_to(ROOT)}`; se usan los valores por defecto.")
    return {}

def write_json(path, values, overwrite=True):
    """Escribe en un temporal y lo publica de una vez: un fallo a mitad no deja el archivo corrupto.
    Con overwrite=False falla (FileExistsError) si el archivo ya existe."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(values, f, ensure_ascii=False, indent=2)
            f.write("\n")
        if overwrite:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def merge(default, saved):
    """Valores guardados sobre los por defecto; ignora llaves desconocidas y tipos distintos."""
    if isinstance(default, dict):
        saved = saved if isinstance(saved, dict) else {}
        return {k: merge(v, saved.get(k, v)) for k, v in default.items()}
    if isinstance(default, list):
        ok = isinstance(saved, list) and len(saved) == len(default)
        return [merge(d, s) for d, s in zip(default, saved)] if ok else copy.deepcopy(default)
    if isinstance(default, (int, float)) and isinstance(saved, (int, float)) and not isinstance(saved, bool):
        return type(default)(saved)
    return copy.deepcopy(default)

# ---------------- Versiones ----------------
def user_slug(name):
    plain = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", plain.strip().casefold()).strip("_")

def version_path(name):
    return VERSIONS_DIR / f"{name}.json"

def load_version(name):
    """Contenido validado de una versión: meta, rie, arbol y mitigantes."""
    raw = read_json(version_path(name))
    arbol = raw.get("arbol") if isinstance(raw.get("arbol"), dict) else {}
    mitigantes = raw.get("mitigantes") if isinstance(raw.get("mitigantes"), dict) else {}
    return {
        "meta": raw.get("meta") if isinstance(raw.get("meta"), dict) else {},
        "rie": merge(DEFAULT_PARAMS, raw.get("rie")),
        "arbol": {k: v for k, v in arbol.items() if v in DECISION_OPTIONS},
        "mitigantes": {k: {m: int(bool(v.get(m, 0))) for m in ("avalista", "garantia")}
                       for k, v in mitigantes.items() if isinstance(v, dict)},
    }

def list_versions():
    """Versión 1 primero y luego las de los usuarios, de la más reciente a la más antigua."""
    others = []
    for path in VERSIONS_DIR.glob("*.json"):
        if path.stem == BASE_VERSION:
            continue
        meta = read_json(path).get("meta", {})
        others.append({"nombre": path.stem, "usuario": meta.get("usuario", ""), "fecha": meta.get("fecha", ""),
                       "nota": meta.get("nota", "")})
    others.sort(key=lambda v: v["fecha"], reverse=True)
    return [{"nombre": BASE_VERSION, "usuario": "", "fecha": "", "nota": ""}] + others

def snapshot():
    ensure_session()
    return {"rie": copy.deepcopy(st.session_state[RIE_STATE]),
            "arbol": dict(st.session_state[ARBOL_DECISION_STATE]),
            "mitigantes": copy.deepcopy(st.session_state[CONDICIONES_STATE])}

def clear_editors():
    for k in [k for k in st.session_state if str(k).startswith(EDITOR_PREFIXES)]:
        del st.session_state[k]

def apply_version(name):
    """Carga la versión en la sesión: reemplaza los parámetros de todas las hojas."""
    content = load_version(name)
    st.session_state[RIE_STATE] = content["rie"]
    st.session_state[ARBOL_DECISION_STATE] = content["arbol"]
    st.session_state[CONDICIONES_STATE] = content["mitigantes"]
    st.session_state[ACTIVE_STATE] = name
    clear_editors()

def ensure_session():
    if ACTIVE_STATE not in st.session_state:
        apply_version(BASE_VERSION)

def pending_changes():
    content = load_version(st.session_state[ACTIVE_STATE])
    content.pop("meta")
    return snapshot() != content

def save_version(user, note):
    """Guarda la sesión como <usuario>_v<N>.json con el siguiente N libre para ese usuario."""
    slug = user_slug(user)
    numbers = [int(m.group(1)) for p in VERSIONS_DIR.glob(f"{slug}_v*.json")
               if (m := re.fullmatch(rf"{re.escape(slug)}_v(\d+)", p.stem))]
    content = {"meta": {"usuario": user.strip(), "fecha": datetime.now().isoformat(timespec="seconds"),
                        "nota": note.strip(), "basada_en": st.session_state[ACTIVE_STATE]}, **snapshot()}
    n = max(numbers, default=0) + 1
    while True:
        name = f"{slug}_v{n}"
        try:
            # Sin sobrescribir: si otra sesión tomó el mismo número, se usa el siguiente.
            write_json(version_path(name), content, overwrite=False)
            return name
        except FileExistsError:
            n += 1

def delete_version(name, user):
    meta = read_json(version_path(name)).get("meta", {})
    if name == BASE_VERSION or user_slug(meta.get("usuario", "")) != user_slug(user):
        return False
    version_path(name).unlink(missing_ok=True)
    return True

def bind(key, get, set_):
    """Liga un widget a un estado propio. Al cambiar de hoja Streamlit trata el widget como nuevo
    (aunque su llave siga en la sesión), así que la llave se siembra en cada ejecución y el
    on_change copia lo que escribe el usuario antes de que corra la hoja."""
    st.session_state[key] = get()
    return {"key": key, "on_change": lambda: set_(st.session_state[key])}

# ---------------- Estado compartido por las hojas ----------------
def rie_params():
    """Parámetros RIE de la sesión (versión activa más lo editado en la hoja RIE)."""
    ensure_session()
    return st.session_state[RIE_STATE]

def arbol_decisions():
    """Decisión por rama de la sesión (versión activa más lo editado en la hoja Árbol)."""
    ensure_session()
    return st.session_state[ARBOL_DECISION_STATE]

def mitigante_conditions():
    """Mitigantes exigidos por rama de la sesión (versión activa más lo editado en la hoja Mitigantes)."""
    ensure_session()
    return st.session_state[CONDICIONES_STATE]

# ---------------- Barra lateral ----------------
def version_label(version):
    if version["nombre"] == BASE_VERSION:
        return "Versión 1 (base)"
    fecha = version["fecha"].replace("T", " ")[:16]
    return " · ".join(x for x in [version["nombre"], fecha, version["nota"]] if x)

def version_sidebar():
    """Selector de versiones. Va al final de cada hoja para que el aviso de cambios sin guardar
    incluya lo editado en esa misma ejecución."""
    ensure_session()
    versions = {v["nombre"]: v for v in list_versions()}
    active = st.session_state[ACTIVE_STATE]
    if active not in versions:  # la versión activa fue eliminada
        active = st.session_state[ACTIVE_STATE] = BASE_VERSION
    if st.session_state.get(SELECT_STATE) not in versions:
        st.session_state[SELECT_STATE] = active
    pending = pending_changes()

    def reload(message=None):
        st.session_state[SELECT_STATE] = st.session_state[ACTIVE_STATE]
        if message:
            st.session_state[MESSAGE_STATE] = message
        st.rerun()

    with st.sidebar.container(border=True):
        st.markdown("**Versión de parámetros**")
        st.caption(f"Activa: **{version_label(versions[active])}**"
                   + (" · ⚠️ con cambios sin guardar" if pending else ""))
        if MESSAGE_STATE in st.session_state:
            st.success(st.session_state.pop(MESSAGE_STATE))
        selected = st.selectbox("Versiones", list(versions), format_func=lambda n: version_label(versions[n]),
            **bind("ver_seleccion", lambda: st.session_state[SELECT_STATE],
                   lambda v: st.session_state.__setitem__(SELECT_STATE, v)))
        user = st.text_input("Tu nombre", placeholder="Para guardar o eliminar versiones",
            **bind("ver_usuario", lambda: st.session_state.get(USER_STATE, ""),
                   lambda v: st.session_state.__setitem__(USER_STATE, v)))
        own = (selected != BASE_VERSION and bool(user_slug(user))
               and user_slug(versions[selected]["usuario"]) == user_slug(user))

        c_load, c_delete = st.columns(2)
        with c_load:
            if st.button("Cargar", key="ver_cargar", width="stretch", disabled=selected == active and not pending,
                         help="Reemplaza los parámetros de todas las hojas por los de la versión elegida."):
                apply_version(selected)
                reload(f"Versión cargada: {version_label(versions[selected])}.")
        with c_delete:
            with st.popover("Eliminar", width="stretch", disabled=not own,
                            help="Solo puedes eliminar tus versiones; la versión 1 no se elimina."):
                st.warning(f"¿Eliminar {selected}? No se puede deshacer.")
                if st.button("Sí, eliminar", key="ver_eliminar", type="primary", width="stretch"):
                    delete_version(selected, user)
                    reload(f"Versión {selected} eliminada.")
        if pending and st.button("Descartar cambios", key="ver_descartar", width="stretch",
                                 help="Vuelve a los parámetros de la versión activa."):
            apply_version(active)
            reload("Cambios descartados.")

        note = st.text_input("Nota (opcional)", key="ver_nota", placeholder="Ej.: PTI más estricto")
        if st.button("Guardar como nueva versión", key="ver_guardar", type="primary", width="stretch",
                     disabled=not user_slug(user), help="Escribe tu nombre para guardar."):
            name = save_version(user, note)
            st.session_state[ACTIVE_STATE] = name
            st.session_state.pop("ver_nota", None)
            reload(f"Guardada como {name}.")
        st.caption("Incluye los parámetros RIE, las decisiones del Árbol y los mitigantes por rama.")
