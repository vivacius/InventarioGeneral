import streamlit as st
import pandas as pd
import pygsheets
from datetime import datetime
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import cv2
from pyzbar import pyzbar
import av

# ------------------------ Escáner por cámara ------------------------ #
class BarcodeScanner(VideoTransformerBase):
    def __init__(self):
        self.last_code = None

    def transform(self, frame):
        img = frame.to_ndarray(format="bgr24")
        barcodes = pyzbar.decode(img)

        for barcode in barcodes:
            barcode_data = barcode.data.decode("utf-8")
            self.last_code = barcode_data
            (x, y, w, h) = barcode.rect
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.putText(img, barcode_data, (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return img

# ------------------------ Conexión a Google Sheets ------------------------ #
gc = pygsheets.authorize(service_file='credenciales.json')
spreadsheet = gc.open('InventarioGeneral')

productos_sheet = spreadsheet.worksheet_by_title('productos')
bodega1_sheet = spreadsheet.worksheet_by_title('inventario_bodega1')
bodega2_sheet = spreadsheet.worksheet_by_title('inventario_bodega2')
movimientos_sheet = spreadsheet.worksheet_by_title('movimientos')

# ------------------------ Interfaz ------------------------ #
st.set_page_config(page_title="Inventario", layout="wide")
st.title("📦 Sistema de Inventario con Código de Barras")

menu = st.sidebar.selectbox("Menú", ["📥 Registrar Movimiento", "📊 Ver Inventario"])

# ------------------------ Registrar Movimiento ------------------------ #
if menu == "📥 Registrar Movimiento":
    df_productos = productos_sheet.get_as_df()

    st.subheader("Ingreso de productos por escáner o manual")
    metodo = st.radio("Selecciona el método de ingreso del código de barras", ["Escanear con cámara", "Escribir manualmente"])

    codigo = None
    if metodo == "Escanear con cámara":
        st.info("Activa tu cámara y escanea el código de barras")
        ctx = webrtc_streamer(key="barcode", video_transformer_factory=BarcodeScanner)
        if ctx.video_transformer:
            codigo = ctx.video_transformer.last_code
    else:
        codigo = st.text_input("Ingresa el código de barras manualmente")

    if codigo:
        producto = df_productos[df_productos['Codigo_Barras'].astype(str) == codigo]

        if not producto.empty:
            detalle = producto.iloc[0]['Detalle']
            inventariable = producto.iloc[0]['Es_Inventariable']

            st.success(f"Producto detectado: {detalle}")
            st.write(f"📦 ¿Inventariable?: {inventariable}")

            col1, col2 = st.columns(2)
            with col1:
                terminado = st.radio("¿Es un producto terminado?", ["Sí", "No"])
                movimiento = st.radio("Tipo de movimiento", ["Entrada", "Salida"])
            with col2:
                cantidad = st.number_input("Cantidad", min_value=1, step=1)
                usuario = st.text_input("Usuario responsable")

            observaciones = st.text_area("Observaciones (opcional)")

            if st.button("✅ Registrar movimiento"):
                bodega = "Bodega 2" if terminado == "Sí" else "Bodega 1"
                hoja_inventario = bodega2_sheet if terminado == "Sí" else bodega1_sheet
                df_inv = hoja_inventario.get_as_df()

                if codigo in df_inv['Codigo_Barras'].astype(str).values:
                    idx = df_inv[df_inv['Codigo_Barras'].astype(str) == codigo].index[0]
                    cantidad_actual = df_inv.at[idx, 'Cantidad']
                    cantidad_nueva = cantidad_actual + cantidad if movimiento == "Entrada" else max(cantidad_actual - cantidad, 0)
                    df_inv.at[idx, 'Cantidad'] = cantidad_nueva
                else:
                    nueva_fila = {'Codigo_Barras': codigo, 'Detalle': detalle, 'Cantidad': cantidad if movimiento == "Entrada" else 0}
                    df_inv = pd.concat([df_inv, pd.DataFrame([nueva_fila])], ignore_index=True)

                hoja_inventario.set_dataframe(df_inv, (1,1))

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
                movimientos_sheet.set_dataframe(df_mov, (1,1))

                st.success("✅ Movimiento registrado correctamente")
        else:
            st.error("❌ Código no encontrado en la hoja de productos.")

# ------------------------ Ver Inventario ------------------------ #
elige = st.sidebar.selectbox("Seleccionar Bodega", ["Bodega 1", "Bodega 2"])

if menu == "📊 Ver Inventario":
    hoja = bodega1_sheet if elige == "Bodega 1" else bodega2_sheet
    df_inv = hoja.get_as_df()

    st.subheader(f"Inventario actual - {elige}")
    st.dataframe(df_inv.style.format({"Cantidad": "{:,.0f}"}), use_container_width=True)

    total_items = df_inv['Cantidad'].sum()
    total_productos = df_inv.shape[0]

    col1, col2 = st.columns(2)
    col1.metric("Total de productos únicos", total_productos)
    col2.metric("Cantidad total en inventario", total_items)

    st.caption("Solo se muestran cantidades y detalles, sin precios ni datos financieros.")
else:
        st.error("❌ Código no encontrado en la hoja de productos.")
#python -m streamlit run c:/Users/sacor/Downloads/app_inventario2.py