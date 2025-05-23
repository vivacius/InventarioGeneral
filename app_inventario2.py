import streamlit as st
import pandas as pd
import pygsheets
import json
from datetime import datetime
from streamlit_js_events import streamlit_js_events

# --- Autenticación Google Sheets usando GOOGLE_CREDENTIALS_JSON ---
json_creds = st.secrets["GOOGLE_CREDENTIALS_JSON"]
creds_dict = json.loads(json_creds)

gc = pygsheets.authorize(service_account_info=creds_dict)
spreadsheet = gc.open('InventarioGeneral')

productos_sheet = spreadsheet.worksheet_by_title('productos')
bodega1_sheet = spreadsheet.worksheet_by_title('inventario_bodega1')
bodega2_sheet = spreadsheet.worksheet_by_title('inventario_bodega2')
movimientos_sheet = spreadsheet.worksheet_by_title('movimientos')

df_productos = productos_sheet.get_as_df()

# --- JS para cámara y escaneo automático con jsQR y streamlit_js_events ---
JS_CODE = """
async function startScanner() {
  const video = document.createElement('video');
  video.setAttribute('playsinline', 'true');
  video.style.width = '100%';
  video.style.height = 'auto';
  document.body.appendChild(video);

  const canvasElement = document.createElement('canvas');
  const canvas = canvasElement.getContext('2d');

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    video.srcObject = stream;
    await video.play();

    const scan = () => {
      if (video.readyState === video.HAVE_ENOUGH_DATA) {
        canvasElement.height = video.videoHeight;
        canvasElement.width = video.videoWidth;
        canvas.drawImage(video, 0, 0, canvasElement.width, canvasElement.height);
        const imageData = canvas.getImageData(0, 0, canvasElement.width, canvasElement.height);
        const code = jsQR(imageData.data, imageData.width, imageData.height, { inversionAttempts: "dontInvert" });

        if (code) {
          window.streamlitJsEvents.emit("barcodeScanned", code.data);
          stream.getTracks().forEach(track => track.stop());
          return;
        }
      }
      requestAnimationFrame(scan);
    };
    scan();

  } catch (e) {
    window.streamlitJsEvents.emit("error", e.toString());
  }
}

const script = document.createElement('script');
script.src = "https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js";
script.onload = startScanner;
document.head.appendChild(script);
"""

st.title("📦 Aplicación de Inventario con Código de Barras")

# Control para reiniciar el escáner
if "restart_scanner" not in st.session_state:
    st.session_state.restart_scanner = True

if st.session_state.restart_scanner:
    st.info("Activa tu cámara y escanea el código de barras")
    result = streamlit_js_events(js_code=JS_CODE, events=["barcodeScanned", "error"], key="barcode_scanner")
else:
    result = None

codigo = None
if result:
    if "barcodeScanned" in result and result["barcodeScanned"]:
        codigo = result["barcodeScanned"]
        st.session_state.restart_scanner = False
    if "error" in result and result["error"]:
        st.error(f"Error al acceder a la cámara: {result['error']}")

if codigo:
    st.success(f"Código detectado: {codigo}")

    producto = df_productos[df_productos['Codigo_Barras'].astype(str) == codigo]

    if not producto.empty:
        detalle = producto.iloc[0]['Detalle']
        precio = producto.iloc[0]['Precio']
        inventariable = producto.iloc[0]['Es_Inventariable']

        st.success(f"Producto: {detalle}")
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
                nueva_fila = {
                    'Codigo_Barras': codigo,
                    'Detalle': detalle,
                    'Cantidad': cantidad if movimiento == "Entrada" else 0
                }
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
            # Reiniciar escáner para nuevo código
            st.session_state.restart_scanner = True

else:
    if st.session_state.restart_scanner:
        st.write("Escanea un código para comenzar.")
