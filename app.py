import os
from html import escape

from flask import Flask, render_template, request
import mysql.connector
from mysql.connector import Error, IntegrityError

app = Flask(__name__)


# Configuración de conexión.
# En OpenShift se leen de variables de entorno (las del Secret aeropuerto-db-credenciales).
# En local (XAMPP) se usan los valores por defecto.
def get_db_connection():
    return mysql.connector.connect(
        host=os.environ.get('DB_HOST', '127.0.0.1'),
        port=int(os.environ.get('DB_PORT', 3306)),
        user=os.environ.get('MYSQL_USER', 'root'),
        password=os.environ.get('MYSQL_PASSWORD', ''),
        database=os.environ.get('MYSQL_DATABASE', 'SistemaAeropuerto'),
        connection_timeout=10
    )


# Funciones de ayuda
def ejecutar_insert(query, valores):
    """Ejecuta un INSERT. Devuelve None si todo salió bien o un mensaje de error."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query, valores)
        conn.commit()
        cursor.close()
        return None
    except IntegrityError as e:
        return f"Dato duplicado o ID inexistente: {e.msg}"
    except Error as e:
        return f"Error de base de datos: {e.msg}"
    finally:
        if conn and conn.is_connected():
            conn.close()


def obtener_opciones(query):
    """Devuelve una lista de tuplas (id, texto) para llenar un <select>."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(query)
        filas = cursor.fetchall()
        cursor.close()
        return filas
    except Error as e:
        print(f"Error consultando opciones: {e}", flush=True)
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def pagina_mensaje(titulo, detalle="", codigo=200):
    html = f"<h1>{escape(titulo)}</h1>"
    if detalle:
        html += f"<p>{escape(detalle)}</p>"
    html += "<a href='/'>Volver al Inicio</a>"
    return html, codigo


# Ruta de salud (útil para probar que la app está viva)
@app.route('/health')
def health():
    return "ok", 200


# Ruta principal: página con los desplegables
@app.route('/')
def home():
    paises = obtener_opciones(
        "SELECT id_pais, nombre FROM Pais ORDER BY nombre"
    )
    aerolineas = obtener_opciones(
        "SELECT id_aerolinea, nombre FROM Aerolinea ORDER BY nombre"
    )
    aeropuertos = obtener_opciones(
        """SELECT a.id_aeropuerto,
                CONCAT(a.codigo_iata, ' - ', a.nombre, ' (', c.nombre, ')')
        FROM Aeropuerto a
        JOIN Ciudad c ON a.id_ciudad = c.id_ciudad
        ORDER BY c.nombre"""
    )
    return render_template(
        'index.html',
        paises=paises,
        aerolineas=aerolineas,
        aeropuertos=aeropuertos
    )


# Registrar pasajeros
@app.route('/registrar_pasajero', methods=['POST'])
def registrar_pasajero():
    f = request.form

    error = ejecutar_insert(
        """INSERT INTO Pasajero
        (nombres, apellidos, pasaporte, correo, telefono, id_nacionalidad)
        VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            f['nombres'].strip(),
            f['apellidos'].strip(),
            f['pasaporte'].strip(),
            f.get('correo', '').strip() or None,
            f.get('telefono', '').strip() or None,
            f['id_nacionalidad'],
        )
    )

    if error:
        return pagina_mensaje("No se pudo guardar el pasajero", error, 400)
    return pagina_mensaje("¡Pasajero guardado con éxito!")


# Registrar vuelos
@app.route('/registrar_vuelo', methods=['POST'])
def registrar_vuelo():
    f = request.form

    # El origen y el destino no pueden ser el mismo aeropuerto
    if f['id_origen'] == f['id_destino']:
        return pagina_mensaje(
            "El origen y el destino no pueden ser iguales", codigo=400
        )

    # datetime-local envía "2026-11-11T10:30"; MySQL espera "2026-11-11 10:30"
    salida = f['fecha_salida'].replace('T', ' ')
    llegada = f['fecha_llegada'].replace('T', ' ')

    # La llegada debe ser posterior a la salida (el formato ISO se compara como texto)
    if llegada <= salida:
        return pagina_mensaje(
            "La fecha de llegada debe ser posterior a la de salida", codigo=400
        )

    error = ejecutar_insert(
        """INSERT INTO Vuelo
        (codigo_vuelo, id_aerolinea, id_aeropuerto_origen,
            id_aeropuerto_destino, fecha_salida, fecha_llegada)
        VALUES (%s, %s, %s, %s, %s, %s)""",
        (
            f['codigo_vuelo'].strip(),
            f['id_aerolinea'],
            f['id_origen'],
            f['id_destino'],
            salida,
            llegada,
        )
    )

    if error:
        return pagina_mensaje("No se pudo programar el vuelo", error, 400)
    return pagina_mensaje("¡Vuelo programado con éxito!")


if __name__ == '__main__':
    # Solo para pruebas locales. En OpenShift se usa gunicorn (ver Dockerfile).
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
