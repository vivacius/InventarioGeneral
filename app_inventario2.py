import streamlit as st
import pandas as pd
import pygsheets
from datetime import datetime
from streamlit_js_eval import streamlit_js_eval

# --- Autenticación con Google Sheets desde secretos ---
import json
import os

# Guardar el JSON en un archivo temporal para pygsheets
with open("tmp_google_credentials.json", "w") as f:
    f.write(st.secrets["GOOGLE_CREDENTIALS_JSON"])

gc = pygsheets.authorize(service_file="tmp_google_credentials.json")
spreadsheet = gc.open('InventarioGeneral')

# Hojas del Google Sheets
productos_sheet = spreadsheet.worksheet_by_title('productos')
bodega1_sheet = spreadsheet.worksheet_by_title('inventario_bodega1')
bodega2_sheet = spreadsheet.worksheet_by_title('inventario_bodega2')
movimientos_sheet = spreadsheet.worksheet_by_title('movimientos')

# Cargar base de productos
df_productos = productos_sheet.get_as_df()

st.title("📦 Aplicación de Inventario con Código de Barras")

# --- HTML5 QR CODE ---
st.markdown("""
<h5>📸 Escanea el código de barras:</h5>
<div id="reader" width="300px"></div>
<script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>
<script>
    function domReady(fn) {
        if (document.readyState === "interactive" || document.readyState === "complete") {
            fn();
        } else {
            document.addEventListener("DOMContentLoaded", fn);
        }
    }

    domReady(function () {
        let lastResult = "";
        const html5QrCode = new Html5Qrcode("reader");
        html5QrCode.start(
            { facingMode: "environment" },
            {
                fps: 10,
                qrbox: { width: 250, height: 250 }
            },
            (decodedText, decodedResult) => {
                if (decodedText !== lastResult) {
                    lastResult = decodedText;
                    const streamlitEvent = new CustomEvent("streamlit:barcode", {
                        detail: decodedText
                    });
                    window.dispatchEvent(streamlitEvent);
                }
            },
            (errorMessage) => {}
        );
    });
</script>
""", unsafe_allow_html=True)

barcode = streamlit_js_eval(js_expressions="null", events=["barcode"], key="barcode") or {}

codigo = barcode.get("barcode")

if codigo:
    st.success(f"✅ Código escaneado: {codigo}")
    producto = df_productos[df_productos['Codigo_Barras'].astype(str) == codigo]

    if not producto.empty:
        detalle = producto.iloc[0]['Detalle']
        precio = producto.iloc[0]['Precio']
        inventariable = producto.iloc[0]['Es_Inventariable']

        st.write(f"🧾 Producto: **{detalle}**")
        st.write(f"💲 Precio: {precio}")
        st.write(f"📦 ¿Inventariable?: {inventariable}")

        terminado = st.radio("¿Es un producto terminado?", ["Sí", "No"])
        movimiento = st.radio("Tipo de movimiento", ["Entrada", "Salida"])
        cantidad = st.number_input("Cantidad", min_value=1, step=1)
        usuario = st.text_input("Usuario responsable")
        observaciones = st.text_area("Observaciones (opcional)")

        if st.button("Registrar movimiento"):
            bodega = "Bodega 2" if terminado == "Sí" else "Bodega 1"
            hoja_inventario = bodega2_sheet if terminado == "Sí" else bodega1_sheet

            df_inv = hoja_inventario.get_as_df()

            if codigo in df_inv['Codigo_Barras'].astype(str).values:
                idx = df_inv[df_inv['Codigo_Barras'].astype(str) == codigo].index[0]
                cantidad_actual = df_inv.at[idx, 'Cantidad']
                cantidad_nueva = cantidad_actual + cantidad if movimiento == "Entrada" else max(cantidad_actual - cantidad, 0)
                df_inv.at[idx, 'Cantidad'] = cantidad_nueva
            else:
                nueva_fila = {
                    'Codigo_Barras': codigo,
                    'Detalle': detalle,
                    'Cantidad': cantidad if movimiento == "Entrada" else 0
                }
                df_inv = pd.concat([df_inv, pd.DataFrame([nueva_fila])], ignore_index=True)

            hoja_inventario.set_dataframe(df_inv, (1, 1))

            nuevo_movimiento = {
                'Fecha y Hora': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'Codigo_Barras': codigo,
                'Movimiento': movimiento,
                'Cantidad': cantidad,
                'Bodega': bodega,
                'Usuario': usuario,
                'Observaciones': observaciones
            }

            df_mov = movimientos_sheet.get_as_df()
            df_mov = pd.concat([df_mov, pd.DataFrame([nuevo_movimiento])], ignore_index=True)
            movimientos_sheet.set_dataframe(df_mov, (1, 1))

            st.success("✅ Movimiento registrado correctamente.")
    else:
        st.error("❌ Código no encontrado en la hoja de productos.")
else:
    st.info("Esperando que escanees un código...")
