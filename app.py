import streamlit as st
import pandas as pd
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
import io

# 1. CONFIGURACIÓN E INTERFAZ (OCULTA MENÚS)
st.set_page_config(page_title="Conciliador Bancario GNB", layout="wide")

hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("🏦 Concilia GNB @JuanS 🤖")
st.markdown("Diseñado para conciliar de Muchos a un bloque. (Con filtro de moneda)")

# 2. CARGA DE ARCHIVO
# Se añade soporte por si suben el CSV directo en lugar del Excel
archivo_subido = st.file_uploader("Sube tu archivo (.xlsx o .csv)", type=['xlsx', 'csv'])

if archivo_subido is not None:
    try:
        if archivo_subido.name.endswith('.csv'):
            df = pd.read_csv(archivo_subido)
        else:
            df = pd.read_excel(archivo_subido)
            
        st.info("Archivo cargado con éxito. Procesando datos...")

        # Identificamos las columnas por su posición como solicitaste (A=0, B=1...)
        # Columna D = índice 3 (Clave contabiliz.)
        # Columna I = índice 8 (Importe en moneda local)
        # Columna L = índice 11 (Criterio: Pesos o USD)
        col_d = df.columns[3]  
        col_i = df.columns[8]  
        col_l = df.columns[11] 

        # Limpiamos y estandarizamos la columna L (mayúsculas y sin espacios)
        df[col_l] = df[col_l].astype(str).str.strip().str.upper()

        # Filtro de Moneda en la interfaz
        monedas = df[col_l].unique()
        moneda_seleccionada = st.selectbox("Selecciona la moneda a conciliar (Columna L):", monedas)

        # Filtramos el dataframe SOLAMENTE por la moneda que escogió el usuario
        df_filtrado = df[df[col_l] == moneda_seleccionada].copy()

        # Separar datos: Buscamos registros con Clave 40 en la moneda seleccionada
        df_40 = df_filtrado[df_filtrado[col_d] == 40].reset_index(drop=False)
        values_40 = df_40[col_i].values
        
        # El objetivo es la suma de todas las claves 50 de esa misma moneda
        target_sum = df_filtrado[df_filtrado[col_d] == 50][col_i].sum()
        
        st.write(f"**Objetivo de suma (Clave 50 en {moneda_seleccionada}):** ${target_sum:,.2f}")
        st.write(f"**Registros candidatos (Clave 40 en {moneda_seleccionada}):** {len(values_40)}")

        # 3. LÓGICA DE CONCILIACIÓN (MILP)
        if st.button("🚀 Ejecutar Conciliación"):
            with st.spinner('Buscando la combinación exacta...'):
                n = len(values_40)
                
                if n == 0:
                    st.warning(f"No hay registros con Clave 40 para la moneda {moneda_seleccionada}.")
                else:
                    # TRUCO DE PRECISIÓN MILP: Convertir todo a centavos (enteros) 
                    # para evitar el error clásico de decimales en Python
                    values_40_cents = np.round(values_40 * 100).astype(int)
                    target_cents = int(round(target_sum * 100))

                    # Configurar modelo matemático
                    c = np.zeros(n)
                    A = np.atleast_2d(values_40_cents)
                    
                    # Restricción: La suma de los "centavos" debe ser exacta
                    constraints = LinearConstraint(A, target_cents, target_cents)
                    bounds = Bounds(0, 1)
                    integrality = np.ones(n) # Variables binarias (1 lo toma, 0 lo descarta)
                    
                    # Se añade 'time_limit' de 60 seg para evitar bloqueos si hay muchísimos datos
                    res = milp(c=c, constraints=constraints, bounds=bounds, integrality=integrality, options={'time_limit': 60})
                    
                    if res.success:
                        # Preparamos la columna de resultados en el DF original
                        if 'Conciliacion_Exacta' not in df.columns:
                            df['Conciliacion_Exacta'] = "No Conciliado"
                            
                        # Rescatar los índices originales de los registros seleccionados
                        selected_indices = np.where(np.round(res.x) == 1)[0]
                        selected_original_indices = df_40.iloc[selected_indices]['index'].values
                        
                        # Marcamos las claves 40 que cuadraron
                        df.loc[selected_original_indices, 'Conciliacion_Exacta'] = f"Conciliado (Grupo 40 - {moneda_seleccionada})"
                        
                        # Marcamos todas las claves 50 de esa moneda
                        indices_50 = df_filtrado[df_filtrado[col_d] == 50].index
                        df.loc[indices_50, 'Conciliacion_Exacta'] = f"Conciliado (Grupo 50 - {moneda_seleccionada})"
                        
                        st.success(f"¡Logrado! Se encontraron {len(selected_indices)} registros que cuadran perfectamente.")
                        st.balloons()
                        
                        # 4. DESCARGA DE RESULTADOS
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False)
                        
                        st.download_button(
                            label="📥 Descargar Excel Conciliado",
                            data=output.getvalue(),
                            file_name=f"Conciliacion_GNB_{moneda_seleccionada}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.error("No se encontró una combinación exacta. Prueba revisar los datos base.")
                        
    except Exception as e:
        st.error(f"Error técnico. Verifica que el archivo tenga al menos 12 columnas. Detalle: {e}")
