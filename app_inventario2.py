import streamlit as st
import pandas as pd
import pygsheets
from datetime import datetime
from pyzxing import BarCodeReader
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import cv2
import numpy as np

# Autenticación con Google Sheets
import json
import os

# Leer las credenciales desde Streamlit secrets
cred_json = st.secrets["GOOGLE_CREDENTIALS_JSON"]
with open("temp_creds.json", "w") as f:
    json.dump(cred_json, f)

gc = pygsheets.authorize(service_file='temp_creds.json')
spreadsheet = gc.open('InventarioGeneral')

# Hojas
productos_sheet = spreadsheet.worksheet_by_title('productos')
bodega1_sheet = spreadsheet.worksheet_by_title('inventario_bodega1')
bodega2_sheet = spreadsheet.worksheet_by_title('inventario_bodega2')
movimientos_sheet = spreadsheet.worksheet_by_title('movimientos')
df_productos = productos_sheet.get_as_df()

# Interfaz
st.title("📦 Inventario con escáner de códigos de barras")

class VideoTransformer(VideoTransformerBase):
    def __init__(self):
        self.reader = BarCodeReader()

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")

        # Convertir la imagen a escala de grises para mayor precisión
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Detectar el código de barras
        barcodes = self.reader.decode_array(gray)

        if barcodes:
            for barcode in barcodes:
                decoded_data = barcode[0]
                st.session_state.scanned_code = decoded_data
                st.success(f"Código escaneado: {decoded_data}")
                
        return img

if 'scanned_code' not in st.session_state:
    st.session_state.scanned_code = None

menu = st.sidebar.radio("Menú", ["📷 Escanear y Registrar", "📊 Ver Inventario"])

if menu == "📷 Escanear y Registrar":
    st.subheader("Escanea el código de barras con tu cámara")

    webrtc_streamer(key="example", video_transformer_factory=VideoTransformer)

    if st.session_state.scanned_code:
        codigo = st.session_state.scanned_code
        producto = df_productos[df_productos['Codigo_Barras'].astype(str) == codigo]

        if not producto.empty:
            detalle = producto.iloc[0]['Detalle']
            precio = producto.iloc[0]['Precio']
            inventariable = producto.iloc[0]['Es_Inventariable']

            st.write(f"📝 Producto: {detalle}")
            st.write(f"💲 Precio: {precio}")
            st.write(f"📦 ¿Inventariable?: {inventariable}")

            terminado = st.radio("¿Es un producto terminado?", ["Sí", "No"])
            movimiento = st.radio("Tipo de movimiento", ["Entrada", "Salida"])
            cantidad = st.number_input("Cantidad", min_value=1, step=1)
            usuario = st.text_input("Usuario responsable")
            observaciones = st.text_area("Observaciones (opcional)")

            if st.button("Registrar movimiento"):
                hoja = bodega2_sheet if terminado == "Sí" else bodega1_sheet
                bodega = "Bodega 2" if terminado == "Sí" else "Bodega 1"
                df_inv = hoja.get_as_df()

                if codigo in df_inv['Codigo_Barras'].astype(str).values:
                    idx = df_inv[df_inv['Codigo_Barras'].astype(str) == codigo].index[0]
                    cantidad_actual = df_inv.at[idx, 'Cantidad']
                    nueva_cantidad = cantidad_actual + cantidad if movimiento == "Entrada" else max(cantidad_actual - cantidad, 0)
                    df_inv.at[idx, 'Cantidad'] = nueva_cantidad
                else:
                    nueva_fila = {
                        'Codigo_Barras': codigo,
                        'Detalle': detalle,
                        'Cantidad': cantidad if movimiento == "Entrada" else 0
                    }
                    df_inv = pd.concat([df_inv, pd.DataFrame([nueva_fila])], ignore_index=True)

                hoja.set_dataframe(df_inv, (1,1))

                nuevo_mov = {
                    'Fecha y Hora': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'Codigo_Barras': codigo,
                    'Movimiento': movimiento,
                    'Cantidad': cantidad,
                    'Bodega': bodega,
                    'Usuario': usuario,
                    'Observaciones': observaciones
                }

                df_mov = movimientos_sheet.get_as_df()
                df_mov = pd.concat([df_mov, pd.DataFrame([nuevo_mov])], ignore_index=True)
                movimientos_sheet.set_dataframe(df_mov, (1,1))

                st.success("✅ Movimiento registrado con éxito")
        else:
            st.error("❌ Código no encontrado en la hoja de productos.")

elif menu == "📊 Ver Inventario":
    st.subheader("Selecciona la bodega a visualizar")
    elige = st.selectbox("Bodega", ["Bodega 1", "Bodega 2"])
    hoja = bodega1_sheet if elige == "Bodega 1" else bodega2_sheet
    df_inv = hoja.get_as_df()

    st.dataframe(df_inv.style.format({"Cantidad": "{:,.0f}"}), use_container_width=True)

    total_items = df_inv['Cantidad'].sum()
    total_productos = df_inv.shape[0]

    col1, col2 = st.columns(2)
    col1.metric("Total de productos únicos", total_productos)
    col2.metric("Cantidad total en inventario", total_items)

    st.caption("Solo se muestran cantidades y detalles, sin precios ni datos financieros.")

#python -m streamlit run c:/Users/sacor/Downloads/app_inventario2.py
