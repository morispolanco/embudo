import io
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st


# -----------------------------
# Configuracion general
# -----------------------------
st.set_page_config(
    page_title="Embudo de Ventas",
    page_icon="📊",
    layout="wide",
)


# -----------------------------
# Credenciales de administracion
# Recomendacion: mover estas claves a st.secrets en produccion.
# -----------------------------
ADMIN_USER = "mpolanco"
ADMIN_PASSWORD = "Mita1962"


DEFAULT_STAGE_ORDER = [
    "Lead",
    "Calificado",
    "Propuesta",
    "Negociacion",
    "Cierre",
]


# -----------------------------
# Utilidades
# -----------------------------
def init_state() -> None:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "is_admin" not in st.session_state:
        st.session_state.is_admin = False
    if "username" not in st.session_state:
        st.session_state.username = ""
    if "stage_order" not in st.session_state:
        st.session_state.stage_order = DEFAULT_STAGE_ORDER.copy()
    if "data" not in st.session_state:
        st.session_state.data = None


@st.cache_data(show_spinner=False)
def load_file(uploaded_file) -> pd.DataFrame:
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("Formato no soportado. Usa CSV o Excel.")
    return df


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def parse_dates(df: pd.DataFrame, date_col: str) -> pd.DataFrame:
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    return df


def require_columns(df: pd.DataFrame, required: list[str]) -> list[str]:
    return [c for c in required if c not in df.columns]


def stage_progress(df: pd.DataFrame, stage_col: str, stage_order: list[str]) -> pd.DataFrame:
    counts = []
    for stage in stage_order:
        counts.append((stage, int((df[stage_col].astype(str).str.strip() == stage).sum())))
    result = pd.DataFrame(counts, columns=["etapa", "cantidad"])
    result["conversión_vs_anterior"] = result["cantidad"].shift(-1) / result["cantidad"].replace(0, np.nan)
    result["abandono_vs_anterior"] = 1 - result["conversión_vs_anterior"]
    return result


def funnel_kpis(funnel_df: pd.DataFrame) -> dict:
    first = int(funnel_df.iloc[0]["cantidad"]) if len(funnel_df) else 0
    last = int(funnel_df.iloc[-1]["cantidad"]) if len(funnel_df) else 0
    total_conversion = (last / first) if first else 0
    biggest_drop = None
    if len(funnel_df) > 1:
        temp = funnel_df.iloc[:-1].copy()
        temp["drop"] = temp["cantidad"] - temp["cantidad"].shift(-1)
        temp["drop_pct"] = temp["drop"] / temp["cantidad"].replace(0, np.nan)
        biggest_drop = temp.sort_values("drop_pct", ascending=False).iloc[0]
    return {
        "inicio": first,
        "final": last,
        "conversion_total": total_conversion,
        "mayor_fuga": biggest_drop,
    }


def safe_to_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


# -----------------------------
# Autenticacion
# -----------------------------
def login_view() -> None:
    st.title("📊 Embudo de Ventas")
    st.caption("Acceso para usuarios y administradores")

    c1, c2 = st.columns(2)
    with c1:
        with st.form("login_form"):
            username = st.text_input("Usuario")
            password = st.text_input("Contraseña", type="password")
            submitted = st.form_submit_button("Entrar")

        if submitted:
            if username == ADMIN_USER and password == ADMIN_PASSWORD:
                st.session_state.authenticated = True
                st.session_state.is_admin = True
                st.session_state.username = username
                st.success("Bienvenido, administrador.")
                st.rerun()
            elif username and password:
                st.session_state.authenticated = True
                st.session_state.is_admin = False
                st.session_state.username = username
                st.success(f"Bienvenido, {username}.")
                st.rerun()
            else:
                st.error("Completa usuario y contraseña.")

    with c2:
        st.info(
            """
            Esta aplicación permite:
            - cargar datos de ventas,
            - calcular conversión por etapa,
            - detectar fugas,
            - rankear vendedores,
            - y administrar parámetros desde una página protegida.
            """
        )


# -----------------------------
# Carga y validacion de datos
# -----------------------------
def data_loader_view() -> pd.DataFrame | None:
    st.subheader("1. Carga de datos")
    uploaded = st.file_uploader("Sube un archivo CSV o Excel", type=["csv", "xlsx", "xls"])
    if uploaded is None:
        return None

    try:
        df = load_file(uploaded)
        df = normalize_columns(df)
        st.success(f"Archivo cargado: {df.shape[0]} filas y {df.shape[1]} columnas")
        st.dataframe(df.head(20), use_container_width=True)
        return df
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        return None


# -----------------------------
# Analisis del embudo
# -----------------------------
def funnel_analysis_view(df: pd.DataFrame, stage_col: str, salesperson_col: str | None, date_col: str | None) -> None:
    st.subheader("2. Analisis del embudo")

    if date_col and date_col in df.columns:
        df = parse_dates(df, date_col)

    funnel_df = stage_progress(df, stage_col, st.session_state.stage_order)
    kpis = funnel_kpis(funnel_df)

    k1, k2, k3 = st.columns(3)
    k1.metric("Registros iniciales", f"{kpis['inicio']:,}")
    k2.metric("Registros finales", f"{kpis['final']:,}")
    k3.metric("Conversión total", f"{kpis['conversion_total']:.1%}")

    st.markdown("### Evolución por etapa")
    fig = px.funnel(
        funnel_df,
        y="etapa",
        x="cantidad",
        title="Embudo de ventas",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Conversión y abandono")
    display_df = funnel_df.copy()
    display_df["conversión_vs_anterior"] = display_df["conversión_vs_anterior"].map(lambda x: f"{x:.1%}" if pd.notna(x) else "-")
    display_df["abandono_vs_anterior"] = display_df["abandono_vs_anterior"].map(lambda x: f"{x:.1%}" if pd.notna(x) else "-")
    st.dataframe(display_df, use_container_width=True)

    if kpis["mayor_fuga"] is not None:
        st.warning(
            f"Mayor fuga detectada en '{kpis['mayor_fuga']['etapa']}' con una pérdida aproximada de {kpis['mayor_fuga']['abandono_vs_anterior']:.1%}."
        )

    if salesperson_col and salesperson_col in df.columns:
        st.markdown("### Ranking de vendedores")
        last_stage = st.session_state.stage_order[-1]
        tmp = df.copy()
        tmp["cerrado"] = tmp[stage_col].astype(str).str.strip().eq(last_stage).astype(int)
        ranking = (
            tmp.groupby(salesperson_col, dropna=False)
            .agg(
                oportunidades=(stage_col, "count"),
                cierres=("cerrado", "sum"),
            )
            .reset_index()
        )
        ranking["tasa_cierre"] = ranking["cierres"] / ranking["oportunidades"].replace(0, np.nan)
        ranking = ranking.sort_values(["tasa_cierre", "cierres"], ascending=False)
        st.dataframe(ranking, use_container_width=True)

        fig2 = px.bar(
            ranking,
            x=salesperson_col,
            y="tasa_cierre",
            title="Tasa de cierre por vendedor",
        )
        st.plotly_chart(fig2, use_container_width=True)

    if date_col and date_col in df.columns:
        st.markdown("### Tendencia temporal")
        temp = df.dropna(subset=[date_col]).copy()
        if not temp.empty:
            temp["mes"] = temp[date_col].dt.to_period("M").astype(str)
            trend = temp.groupby("mes").size().reset_index(name="registros")
            fig3 = px.line(trend, x="mes", y="registros", markers=True, title="Volumen por mes")
            st.plotly_chart(fig3, use_container_width=True)


# -----------------------------
# Administracion
# -----------------------------
def admin_view(df: pd.DataFrame | None) -> None:
    st.subheader("Panel de administrador")
    st.write(f"Usuario autenticado: **{st.session_state.username}**")

    st.markdown("### Configuracion del embudo")
    st.caption("Define el orden de las etapas del proceso comercial.")

    stages_text = st.text_area(
        "Etapas separadas por coma",
        value=", ".join(st.session_state.stage_order),
        help="Ejemplo: Lead, Calificado, Propuesta, Negociacion, Cierre",
    )
    if st.button("Guardar etapas"):
        stages = [s.strip() for s in stages_text.split(",") if s.strip()]
        if len(stages) < 2:
            st.error("Debes definir al menos 2 etapas.")
        else:
            st.session_state.stage_order = stages
            st.success("Etapas actualizadas.")

    st.markdown("### Exportaciones")
    if df is not None:
        st.download_button(
            "Descargar datos en CSV",
            data=safe_to_csv(df),
            file_name="datos_embudo_normalizados.csv",
            mime="text/csv",
        )

    st.markdown("### Reglas de negocio")
    st.write("- Alertar si una etapa cae por debajo del umbral esperado.")
    st.write("- Permitir comparar periodos.")
    st.write("- Mantener auditoria de cambios en configuracion.")


# -----------------------------
# Aplicacion principal
# -----------------------------
def main() -> None:
    init_state()

    if not st.session_state.authenticated:
        login_view()
        return

    with st.sidebar:
        st.header("Navegacion")
        menu = st.radio("Ir a", ["Analisis", "Administracion"] if st.session_state.is_admin else ["Analisis"])
        st.divider()
        st.write(f"Usuario: **{st.session_state.username}**")
        if st.button("Cerrar sesion"):
            st.session_state.authenticated = False
            st.session_state.is_admin = False
            st.session_state.username = ""
            st.rerun()

    if menu == "Administracion" and st.session_state.is_admin:
        admin_view(st.session_state.data)
        return

    st.title("📊 Analisis de Embudo de Ventas")
    st.caption("App empresarial para seguimiento de conversion, fugas y rendimiento comercial.")

    df = data_loader_view()
    st.session_state.data = df
    if df is None:
        st.info("Cargue un archivo para comenzar.")
        st.markdown(
            """
            ### Columnas sugeridas
            - `cliente_id`
            - `etapa`
            - `fecha`
            - `vendedor`
            - `monto`
            """
        )
        return

    required_cols = ["etapa"]
    missing = require_columns(df, required_cols)
    if missing:
        st.error(f"Faltan columnas obligatorias: {', '.join(missing)}")
        st.stop()

    cols = list(df.columns)
    c1, c2, c3 = st.columns(3)
    with c1:
        stage_col = st.selectbox("Columna de etapa", cols, index=cols.index("etapa") if "etapa" in cols else 0)
    with c2:
        salesperson_col = st.selectbox("Columna de vendedor (opcional)", ["(ninguna)"] + cols)
        salesperson_col = None if salesperson_col == "(ninguna)" else salesperson_col
    with c3:
        date_col = st.selectbox("Columna de fecha (opcional)", ["(ninguna)"] + cols)
        date_col = None if date_col == "(ninguna)" else date_col

    st.info(
        "Consejo: el valor de cada etapa debe coincidir con el orden configurado en la administracion."
    )

    funnel_analysis_view(df, stage_col, salesperson_col, date_col)

    with st.expander("Ver ejemplo de estructura de datos"):
        example = pd.DataFrame(
            {
                "cliente_id": [1, 2, 3, 4],
                "etapa": ["Lead", "Calificado", "Propuesta", "Cierre"],
                "fecha": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
                "vendedor": ["Ana", "Ana", "Luis", "Luis"],
                "monto": [1000, 1000, 1500, 1500],
            }
        )
        st.dataframe(example, use_container_width=True)


if __name__ == "__main__":
    main()
