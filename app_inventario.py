import streamlit as st
import pandas as pd
import pygsheets
from datetime import datetime
from streamlit_js_eval import streamlit_js_eval

# Autenticación Google Sheets
import tempfile
import os
import json
# Carga las credenciales desde variable de entorno
credenciales_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

if not credenciales_json:
    st.error("No se encontró la variable de entorno GOOGLE_CREDENTIALS_JSON")
    st.stop()

# Parsear JSON
credenciales_dict = json.loads(credenciales_json)

# Autorizar pygsheets con las credenciales en dict (sin archivo físico)
gc = pygsheets.authorize(service_account_info=credenciales_dict)
spreadsheet = gc.open('InventarioGeneral')

# Autorizar pygsheets con dict
try:
    gc = pygsheets.authorize(service_account_info=credenciales_dict)
    st.success("✅ Autenticación exitosa.")
except Exception as e:
    st.error(f"❌ Error al autorizar Google Sheets: {e}")
    st.stop()

productos_sheet = spreadsheet.worksheet_by_title('productos')
bodega1_sheet = spreadsheet.worksheet_by_title('inventario_bodega1')
bodega2_sheet = spreadsheet.worksheet_by_title('inventario_bodega2')
movimientos_sheet = spreadsheet.worksheet_by_title('movimientos')

df_productos = productos_sheet.get_as_df()

st.title("📦 Inventario con Escaneo de Código de Barras (html5-qrcode)")

# Insertar el escaner html5-qrcode y capturar eventos JS
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
                if movimiento == "Entrada":
                    cantidad_nueva = cantidad_actual + cantidad
                else:
                    cantidad_nueva = max(cantidad_actual - cantidad, 0)
                df_inv.at[idx, 'Cantidad'] = cantidad_nueva
            else:
                cantidad_inicial = cantidad if movimiento == "Entrada" else 0
                nueva_fila = {
                    'Codigo_Barras': codigo,
                    'Detalle': detalle,
                    'Cantidad': cantidad_inicial
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
    st.info("📷 Apunta la cámara a un código de barras para escanear automáticamente.")

