import math
import dash
import time
from dash.dependencies import Output, Input
from dash import dcc, html
from datetime import datetime, timedelta
import json
import csv
import tempfile
import plotly.graph_objs as go
from collections import deque
from flask import Flask, request, jsonify, g
from flask_cors import CORS  # Import CORS
from bson import ObjectId  # For handling MongoDB IDs
from pymongo import MongoClient
import numpy as np
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
import TestDrive
import Service
import jwt
from functools import wraps
from werkzeug.utils import secure_filename
import os

server = Flask(__name__)
server.config['SECRET_KEY'] = 'supersecretkey'  # Chiave segreta per JWT
CORS(server, resources={r"/*": {"origins": "*"}})  # Enable CORS

app = dash.Dash(__name__, server=server)

# Configure Flask-Limiter
limiter = Limiter(
    get_remote_address,
    app=server,
    default_limits=["20 per second"]  # Limit to 20 requests per second
)

# Initialize JWTManager
jwt_token = JWTManager(server)

MAX_DATA_POINTS = 1000
UPDATE_FREQ_MS = 100

times = deque(maxlen=MAX_DATA_POINTS)
accel_x = deque(maxlen=MAX_DATA_POINTS)
accel_y = deque(maxlen=MAX_DATA_POINTS)
accel_z = deque(maxlen=MAX_DATA_POINTS)
gyro_x = deque(maxlen=MAX_DATA_POINTS)
gyro_y = deque(maxlen=MAX_DATA_POINTS)
gyro_z = deque(maxlen=MAX_DATA_POINTS)
latitude = deque(maxlen=MAX_DATA_POINTS)
longitude = deque(maxlen=MAX_DATA_POINTS)

app.layout = html.Div(
    [
        dcc.Markdown(
            children="""
            # Live Sensor Readings
            Streamed from Sensor Logger: tszheichoi.com/sensorlogger
        """
        ),
        dcc.Graph(id="live_graph"),
        dcc.Interval(id="counter", interval=UPDATE_FREQ_MS),
    ]
)

client = MongoClient('mongodb://localhost:27017/')
db = client['SmartDrive']
collection_sensor = db['samples']
collection_session = db['session']
collection_user = db['user']
collection_test = db['test']  # Add this line for the 'test' collection

# Funzione per verificare il token JWT
def verify_token(token):
    try:
        payload = jwt.decode(token, server.config['SECRET_KEY'], algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None  # Token scaduto
    except jwt.InvalidTokenError:
        return None  # Token non valido


# Decoratore per verificare l'autenticazione
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')

        if not token:
            return jsonify({'message': 'Token mancante!'}), 401

        token = token.split(" ")[1]  # Formato del token "Bearer <token>"
        payload = verify_token(token)

        if not payload:
            return jsonify({'message': 'Token non valido o scaduto!'}), 401

        # Per accedere ai dati dell'utente
        g.current_user = payload

        # Clear any residual state that might have been cached
        request.current_user = None

        # Aggiungi il payload decodificato alla richiesta per utilizzarlo nel resto della funzione
        request.current_user = payload
        return f(*args, **kwargs)

    return decorated


@app.callback(Output("live_graph", "figure"), Input("counter", "n_intervals"))
def update_graph(_counter):
    data = [
        go.Scatter(x=list(time), y=list(d), name=name)
        for d, name in zip(
            [accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z],
            ["Accel X", "Accel Y", "Accel Z", "Gyro X", "Gyro Y", "Gyro Z"]
        )
    ]

    graph = {
        "data": data,
        "layout": go.Layout(
            {
                "xaxis": {"type": "date"},
                "yaxis": {"title": "Acceleration and Gyro readings"},
            }
        ),
    }
    if len(time) > 0:  # cannot adjust plot ranges until there is at least one data point
        graph["layout"]["xaxis"]["range"] = [min(time), max(time)]
        graph["layout"]["yaxis"]["range"] = [
            min(accel_x + accel_y + accel_z + gyro_x + gyro_y + gyro_z),
            max(accel_x + accel_y + accel_z + gyro_x + gyro_y + gyro_z),
        ]

    return graph

accelerometer_x = 0
accelerometer_y = 0
accelerometer_z = 0
gyroscope_x = 0
gyroscope_y = 0
gyroscope_z = 0
longitude = 0
latitude = 0
speed = 0

free = True

def convert_numpy_int64_to_int(doc):
    """ Convert numpy.int64 to int in a given dictionary """
    for key, value in doc.items():
        if isinstance(value, np.int64):
            doc[key] = int(value)
    return doc

def convert_oid_fields(record):
    """ Convert $oid fields in the record to ObjectId """
    if '_id' in record and '$oid' in record['_id']:
        record['_id'] = ObjectId(record['_id']['$oid'])
    return record

def convert_dates_to_strings(record):
    """ Convert $date fields in the record to ISO 8601 strings """
    for key, value in record.items():
        if isinstance(value, dict) and '$date' in value:
            if isinstance(value['$date'], str):
                record[key] = value['$date']
            else:
                timestamp = value['$date']
                record[key] = datetime.fromtimestamp(timestamp / 1000).isoformat()
    return record

@server.route("/data", methods=["POST"])
def new_data():  # listens to the data streamed from the sensor logger

    # Termino tutte le sessioni dell'utente loggato
    #endUserSessions()

    global longitude, latitude, speed, free, accelerometer_x, accelerometer_y, accelerometer_z, gyroscope_x, gyroscope_y, gyroscope_z

    #print(f'received data: {request.data}')

    # Estrazione del valore di deviceId
    device_id = None

    data = json.loads(request.data)

    # Controlla i campi principali per il deviceId
    for key, value in data.items():
        if key == 'deviceId':
            device_id = value
            print(device_id)
            break

    # Cerco l'utente in base al suo device_id
    idUser = get_user_id_by_device_id(device_id)
    session_id = None

    # Se c'è una sola sessione attiva posso memorizzare i campioni in arrivo
    #if session_status_code == 200:
    if verify_active_session(idUser) == 1:
        session_response, session_status_code = get_active_session(idUser)
        # Se c'è una sola sessione attiva, continua con il metodo
        active_session = session_response.json
        session_id = active_session['_id']
    elif verify_active_session(idUser) == 0:
        session_id = create_new_session_by_smartphone(datetime.now(), 1, idUser)

    if str(request.method) == "POST":
        #print(f'received data: {request.data}')
        #data = json.loads(request.data)
        for d in data['payload']:
            ts = datetime.fromtimestamp(d["time"] / 1000000000)
            if len(times) == 0 or ts > times[-1]:
                times.append(ts)


                # Iteriamo attraverso gli elementi di payload per cercare le informazioni desiderate
                for item in data['payload']:
                    if 'longitude' in item['values'] and 'latitude' in item['values'] and 'speed' in item['values']:
                        longitude = item['values']['longitude']
                        latitude = item['values']['latitude']
                        speed = item['values']['speed']
                        break  # Terminiamo il loop una volta trovati i valori desiderati
                    if item['name'] == 'accelerometer' and 'values' in item and 'x' in item['values']:
                        accelerometer_x = item['values']['x']
                        accelerometer_y = item['values']['y']
                        accelerometer_z = item['values']['z']
                    elif item['name'] == 'gyroscope' and 'values' in item and 'x' in item['values']:
                        gyroscope_x = item['values']['x']
                        gyroscope_y = item['values']['y']
                        gyroscope_z = item['values']['z']

                if latitude != 0 and longitude != 0 and free == True:
                    free = False

                    doc = {"time": ts}

                    # if d.get("name", None) == "accelerometer":
                    #     accel_x.append(d["accelerometer"]["values"]["x"])
                    #     accel_y.append(d["accelerometer"]["values"]["y"])
                    #     accel_z.append(d["accelerometer"]["values"]["z"])
                    # if d.get("name", None) == "gyroscope":
                    #     gyro_x.append(d["gyroscope"]["values"]["x"])
                    #     gyro_y.append(d["gyroscope"]["values"]["y"])
                    #     gyro_z.append(d["gyroscope"]["values"]["z"])
                    #
                    # ac_x = d["accelerometer"]["values"]["x"]
                    # ac_y = d["accelerometer"]["values"]["y"]
                    # ac_z = d["accelerometer"]["values"]["z"]
                    ac_tot = math.sqrt(accelerometer_x**2 + accelerometer_y**2 + accelerometer_z**2)

                    style = TestDrive.calculateStyle(ac_tot, speed)

                    print(session_id)
                    print(accelerometer_x)
                    print(accelerometer_y)
                    print(accelerometer_z)
                    print(ac_tot)
                    print(latitude)
                    print(longitude)
                    print(speed)
                    print(style)

                    time.sleep(1)


                    roll, pitch = Service.madgwick_filter(accelerometer_x, accelerometer_z, accelerometer_z, gyroscope_x, gyroscope_y, gyroscope_z, 1)

                    doc.update({
                        "session_id": session_id,
                        "accel_x": accelerometer_x,
                        "accel_y": accelerometer_y,
                        "accel_z": accelerometer_z,
                        "total_acceleration": ac_tot,
                        "gyro_x": gyroscope_x,
                        "gyro_y": gyroscope_y,
                        "gyro_z": gyroscope_z,
                        "latitude": latitude,
                        "longitude": longitude,
                        "speed": speed,
                        "style": style,
                        "roll": roll,
                        "pitch": pitch,
                        "created_at": datetime.now(),
                        "updated_at": datetime.now()
                    })


                    # Convert numpy.int64 to int in doc before insertion
                    doc = convert_numpy_int64_to_int(doc)
                    collection_sensor.insert_one(doc)

                    # Aggiorno la media degli stili
                    calculateStyleAverage(session_id)

                    #aggiorno la session con i dati relativi alla posizione dell'ultima acquisizione
                    session_object_id = ObjectId(session_id)
                    collection_session.find_one_and_update(
                         {"_id": session_object_id},
                         {"$set": {
                             "latitude": latitude,
                             "longitude": longitude,
                             "updated_at": datetime.now()
                         }})

                    free = True

    #else:
        # Se non ci sono sessioni attive o ci sono più di una, esci dall'if
        #print(f"Errore: {session_response.json['message'] if 'message' in session_response.json else session_response.json['error']}")

    return "success"


def endUserSessions():
    # Estraggo id user dal jwt
    user_id = g.current_user.get('user_id')

    # Cercare tutte le sessioni associate a questo user_id e con status 1
    sessions = collection_session.find({'user_id': user_id, 'status': 1})

    # Lista delle sessioni trovate
    session_ids = [session['_id'] for session in sessions]

    if session_ids:
        # Aggiornare lo stato delle sessioni trovate a 2
        result = collection_session.update_many(
            {'_id': {'$in': session_ids}},
            {'$set': {'status': 2}}
        )


# Verifico che non ci siano sessioni attive
def verify_active_session(idUser):

    active_sessions = list(collection_session.find({"status": 1}, {"user_id": idUser}))

    if len(active_sessions) == 1:
        return 1
    elif len(active_sessions) == 0:
        return 0
    else:
        # Se ci sono più di una sessione attiva
        return 2


# verifica che ci sia una sessione attiva e ritorna il suo id
#@server.route("/session/get_active", methods=["GET"])
def get_active_session(idUser):
    try:
        # Trova tutte le sessioni con status 1
        active_sessions = list(collection_session.find({"status": 1}, {"user_id": idUser}))

        if len(active_sessions) == 1:
            # Se esiste una sola sessione attiva, restituisci il suo ID
            active_session = active_sessions[0]
            active_session['_id'] = str(active_session['_id'])  # Converti ObjectId in stringa per la serializzazione JSON
            return jsonify(active_session), 200
        elif len(active_sessions) == 0:
            # Se non ci sono sessioni attive
            return jsonify({"message": "No active sessions found"}), 404
        else:
            # Se ci sono più di una sessione attiva
            return jsonify({"error": "Multiple active sessions found"}), 409

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# chiamata api per creare una nuova sessione
@server.route("/session/new_session", methods=["POST"])
@token_required
def newSession(newName=None, newStatus=None, idUser=None):

    if newName is None and newStatus is None and idUser is None:
        # Estrarre il nome dalla richiesta API
        name = request.json.get('name')
        status = request.json.get('status')
        user_id = g.current_user.get('user_id')
    else:
        name = newName
        status = newStatus
        user_id = idUser

    # Ottenere la data e ora attuale
    current_time = datetime.now()

    # Creare il documento da inserire nel database
    session_data = {
        'name': name,
        'longitude': '',  # Lasciato vuoto per ora
        'latitude': '',  # Lasciato vuoto per ora
        'user_id': user_id,
        'status': status,
        'style_average': None,
        'created_at': current_time,
        'updated_at': current_time
    }

    # Inserire il documento nella collezione 'session'
    result = collection_session.insert_one(session_data)

    # Verificare se l'inserimento è avvenuto con successo
    if result.inserted_id:
        # Restituire solo l'ID della sessione creata
        print(result.inserted_id)
        return str(result.inserted_id), 201
    else:
        return '', 500


def create_new_session_by_smartphone(name, status, idUser):
    # Ottenere la data e ora attuale
    current_time = datetime.now()

    # Creare il documento da inserire nel database
    session_data = {
        'name': name,
        'longitude': '',  # Lasciato vuoto per ora
        'latitude': '',  # Lasciato vuoto per ora
        'user_id': idUser,
        'status': status,
        'style_average': None,
        'created_at': current_time,
        'updated_at': current_time
    }

    # Inserire il documento nella collezione 'session'
    result = collection_session.insert_one(session_data)

    # Verificare se l'inserimento è avvenuto con successo
    if result.inserted_id:
        # Restituire solo l'ID della sessione creata
        return str(result.inserted_id)
    else:
        raise RuntimeError("Error while inserting session into DB")


# Tramite questo metodo possiamo avere tutte le sessioni relative a un utente (id estratto dal jwt)
@server.route("/session/find_by_user", methods=["GET"])
@token_required
def getSessionsByUser():
    # Estraggo id user dal jwt
    user_id = g.current_user.get('user_id')

    # Cercare tutte le sessioni associate a questo user_id
    sessions = collection_session.find({'user_id': user_id})

    # Convertire i risultati in una lista di dizionari
    session_list = []
    for session in sessions:
        session['_id'] = str(session['_id'])  # Convertire ObjectId in stringa
        session_list.append(session)

    # Restituire la lista di sessioni
    return jsonify(session_list), 200


# find by id
@server.route("/session/<session_id>", methods=["GET"])
def getSession(session_id):
    try:
        # Convertire session_id in ObjectId (necessario per la query)
        session_object_id = ObjectId(session_id)

        # Trovare la sessione con l'ID specificato
        session = collection_session.find_one({'_id': session_object_id})

        if session:
            # Convertire l'ObjectId in una stringa per la serializzazione JSON
            session['_id'] = str(session['_id'])
            # Se la sessione è trovata, restituire il documento come JSON
            return jsonify(session), 200
        else:
            # Se la sessione non è trovata, restituire un messaggio di errore
            return jsonify({'message': 'Session not found'}), 404

    except Exception as e:
        # Gestire eventuali eccezioni durante il recupero della sessione
        return jsonify({'message': str(e)}), 500


# find all
@server.route("/session/find_all", methods=["GET"])
def getAllSessions():
    try:
        # Trovare tutte le sessioni nella collezione
        sessions = list(collection_session.find())

        # Convertire gli ObjectId in stringhe per la serializzazione JSON
        for session in sessions:
            session['_id'] = str(session['_id'])

        # Restituire tutte le sessioni come JSON
        return jsonify(sessions), 200

    except Exception as e:
        # Gestire eventuali eccezioni durante il recupero delle sessioni
        return jsonify({'message': str(e)}), 500


# Tramite questo metodo possiamo attivare una sessione e prepararla alla raccolta dei dati
@server.route("/session/activate/<id>", methods=["PATCH"])
@token_required
def startSession(id):
    try:
        # Verifica se l'ID è un ObjectId valido
        if not ObjectId.is_valid(id):
            return jsonify({"error": "Invalid ObjectId format"}), 400

        # Converti l'ID in ObjectId
        object_id = ObjectId(id)

        # Estrae id user dal JWT
        user_id = g.current_user.get('user_id')

        # Controlla se esiste già un'istanza con status 1 per l'utente
        existing_active_instance = collection_session.find_one({
            "status": 1,
            "user_id": user_id
        })

        if existing_active_instance:
            print("An instance with status 1 already exists.")
            return jsonify({"error": "An instance with status 1 already exists"}), 409

        # Trova l'oggetto con l'ID specificato e stampa il risultato prima dell'aggiornamento
        current_object = collection_session.find_one({"_id": object_id})
        if not current_object:
            print(f"Object with id {id} not found.")
            return jsonify({"error": "Object not found"}), 404

        # Aggiorna lo status a 1 e il campo updated_at
        result = collection_session.find_one_and_update(
            {"_id": object_id},
            {"$set": {
                "status": 1,
                "updated_at": datetime.now()
            }},
            return_document=True
        )

        if result:
            # Restituisci l'oggetto aggiornato
            result['_id'] = str(result['_id'])  # Converte ObjectId in stringa per la serializzazione JSON
            return jsonify(result), 200
        else:
            print(f"Failed to update object with id {id}.")
            return jsonify({"error": "Failed to update object"}), 500

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@server.route("/session/deactivate/<id>", methods=["PATCH"])
@token_required
def endSession(id):
    try:
        # Verifica se l'ID è un ObjectId valido
        if not ObjectId.is_valid(id):
            return jsonify({"error": "Invalid ObjectId format"}), 400

        # Converti l'ID in ObjectId
        object_id = ObjectId(id)

        # Estraggo dal jwt l'id user
        user_id = g.current_user.get('user_id')

        # Trova l'oggetto con l'ID specificato
        current_object = collection_session.find_one({
            "_id": object_id,
            "user_id": user_id
        })

        if not current_object:
            print(f"Object with id {id} not found.")
            return jsonify({"error": "Object not found"}), 404

        # Aggiorna lo status a 2 e il campo updated_at
        result = collection_session.find_one_and_update(
            {"_id": object_id},
            {"$set": {
                "status": 2,
                "updated_at": datetime.now()
            }},
            return_document=True
        )

        if result:
            # Restituisci l'oggetto aggiornato
            result['_id'] = str(result['_id'])  # Converte ObjectId in stringa per la serializzazione JSON
            return jsonify(result), 200
        else:
            print(f"Failed to update object with id {id}.")
            return jsonify({"error": "Failed to update object"}), 500

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


# calcolo lo stile medio dei campioni associati alla stessa sessione
@server.route('/session/style_average/<session_id>', methods=['PATCH'])
def calculateStyleAverage(session_id):
    # Trova la sessione corrispondente all'ID
    session = collection_session.find_one({'_id': ObjectId(session_id)})
    if not session:
        return jsonify({'error': 'Session not found'}), 404

    # Trova tutti i documenti di samples con lo stesso session_id
    samples = collection_sensor.find({'session_id': session_id})

    total_style_sum = 0
    count = 0

    # Calcola la somma dei valori di style
    for sample in samples:
        total_style_sum += sample['style']
        count += 1

    if count == 0:
        return jsonify({'error': 'No samples found for the session'}), 404

    # Calcola la media arrotondando all'intero più vicino
    style_average = round(total_style_sum / count)

    object_id = ObjectId(session_id)

    # Aggiorna lo status a 2 e il campo updated_at
    result = collection_session.find_one_and_update(
        {"_id": object_id},
        {"$set": {
            "style_average": style_average,
            "updated_at": datetime.now()
        }},
        return_document=True
    )

    if result:
        # Restituisci l'oggetto aggiornato
        result['_id'] = str(result['_id'])  # Converte ObjectId in stringa per la serializzazione JSON
        return jsonify(result), 200
    else:
        print(f"Failed to update object with id {id}.")
        return jsonify({"error": "Failed to update object"}), 500


@server.route('/session/delete/<id>', methods=['DELETE'])
def deleteSession(id):
    try:
        # Verifica se l'ID è un ObjectId valido
        if not ObjectId.is_valid(id):
            return jsonify({"error": "Invalid ObjectId format"}), 400

        # Converti l'ID in ObjectId
        object_id = ObjectId(id)

        # Trova e elimina l'oggetto con l'ID specificato
        result = collection_session.delete_one({"_id": object_id})

        if result.deleted_count > 0:
            return jsonify({"message": f"Session with id {id} deleted successfully"}), 200
        else:
            return jsonify({"error": "Session not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# permette di cercare i campioni associati a una sessione
@server.route('/samples/find_by_session/<session_id>', methods=['GET'])
def getSamplesByIdSession(session_id):
    # Esegui la query per estrarre tutti i campioni con lo stesso session_id
    results = collection_sensor.find({"session_id": session_id})

    # Converti i risultati in una lista di dizionari
    samples = [sample for sample in results]
    for sample in samples:
        sample["_id"] = str(sample["_id"])  # Converti ObjectId in stringa

    return jsonify(samples)


# find all per i campioni
@server.route('/samples/find_all', methods=['GET'])
@token_required
def getAllSamples():
    # Esegui la query per estrarre tutti i campioni
    results = collection_sensor.find()

    # Converti i risultati in una lista di dizionari
    samples = [sample for sample in results]
    for sample in samples:
        sample["_id"] = str(sample["_id"])  # Converti ObjectId in stringa

    return jsonify(samples)


# find by id di una sessione
@server.route('/samples/find_by_id/<sample_id>', methods=['GET'])
def getSampleById(sample_id):
    try:
        # Converti l'id in ObjectId
        object_id = ObjectId(sample_id)
    except:
        return jsonify({"error": "Invalid sample_id format"}), 400

    # Esegui la query per trovare il campione con l'_id specificato
    result = collection_sensor.find_one({"_id": object_id})

    if result:
        result["_id"] = str(result["_id"])  # Converti ObjectId in stringa
        return jsonify(result)
    else:
        return jsonify({"error": "Sample not found"}), 404


# Route to edit a session by ID (name only)
@server.route('/session/edit/<id>', methods=['PATCH'])
def editSession(id):
    try:
        # Extract the session name from the request
        name = request.json.get('name')
        if not name:
            return jsonify({"error": "Name is required"}), 400

        # Verify if the ID is a valid ObjectId
        if not ObjectId.is_valid(id):
            return jsonify({"error": "Invalid ObjectId format"}), 400

        # Convert the ID to ObjectId
        object_id = ObjectId(id)

        # Update the session name and updated_at fields
        result = collection_session.find_one_and_update(
            {"_id": object_id},
            {"$set": {
                "name": name,
                "updated_at": datetime.now()
            }},
            return_document=True
        )

        if result:
            # Return the updated object
            result['_id'] = str(result['_id'])  # Convert ObjectId to string for JSON serialization
            return jsonify(result), 200
        else:
            return jsonify({"error": "Session not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route('/user/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({'message': 'Email and password are required'}), 400

    hashed_password = Service.hash_password(password)
    user = collection_user.find_one({"email": email, "password": hashed_password})

    if user:
        # Genera un token JWT con informazioni aggiuntive
        payload = {
            "user_id": str(user["_id"]),  # Converti ObjectId in stringa
            "email": user.get("email", ""),  # Supponendo che 'email' sia un campo nel documento dell'utente
            #"exp": datetime.utcnow() + timedelta(hours=10)  # Token valido per 10 ore
        }
        token = jwt.encode(payload, server.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({'token': token})

    return jsonify({'message': 'Invalid credentials'}), 401


@server.route('/user/new_user', methods=['POST'])
def newUser():
    client = MongoClient('mongodb://localhost:27017/')
    db = client['SmartDrive']
    collection_user = db['user']

    # Estrarre il nome dalla richiesta API
    name = request.json.get('name')
    surname = request.json.get('surname')
    email = request.json.get('email')
    password = request.json.get('password')
    device_id = request.json.get('device_id')

    # Ottenere la data e ora attuale
    current_time = datetime.now()

    # Creare il documento da inserire nel database
    session_data = {
        'name': name,
        'surname': surname,
        'email': email,
        'password': Service.hash_password(password),
        'device_id': device_id,
        'created_at': current_time,
        'updated_at': current_time
    }

    # Inserire il documento nella collezione 'session'
    result = collection_user.insert_one(session_data)

    # Verificare se l'inserimento è avvenuto con successo
    if result.inserted_id:
        # Restituire solo l'ID della sessione creata
        return str(result.inserted_id), 201
    else:
        return '', 500


def get_user_id_by_device_id(device_id):

    # Cerca l'utente con il device_id specificato
    user = collection_user.find_one({'device_id': device_id})

    if user:
        # Ritorna l'ID dell'utente trovato
        return str(user['_id'])
    else:
        # Se non viene trovato nessun utente con il device_id specificato
        return None


@server.route("/user/modify", methods=["PATCH"])
@token_required
def updateUser():
    try:

        # Estraggo dal jwt l'id user
        user_id = g.current_user.get('user_id')
        object_id = ObjectId(user_id)

        # Trova l'utente con l'ID specificato
        user = collection_user.find_one({"_id": object_id})

        if not user:
            return jsonify({"error": "User not found"}), 404

        # Estrarre i campi dal corpo della richiesta
        data = request.get_json()
        name = data.get('name')
        surname = data.get('surname')
        device_id = data.get('device_id')

        # Aggiorna solo i campi specificati
        update_fields = {}
        if name:
            update_fields['name'] = name
        if surname:
            update_fields['surname'] = surname
        if device_id:
            update_fields['device_id'] = device_id
        update_fields['updated_at'] = datetime.now()

        # Aggiorna l'utente nel database
        result = collection_user.find_one_and_update(
            {"_id": object_id},
            {"$set": update_fields},
            return_document=True
        )

        if result:
            # Converte ObjectId in stringa per la serializzazione JSON
            result['_id'] = str(result['_id'])
            return jsonify(result), 200
        else:
            return jsonify({"error": "Failed to update user"}), 500

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route('/user/find_all', methods=['GET'])
def findAll():
    users = list(collection_user.find())

    # Convertire ObjectId in stringa per la serializzazione JSON
    for user in users:
        user['_id'] = str(user['_id'])

    return jsonify(users), 200


@server.route('/user/<id>', methods=['GET'])
def findById(id):

    if not ObjectId.is_valid(id):
        return jsonify({"error": "Invalid ObjectId format"}), 400

    user = collection_user.find_one({"_id": ObjectId(id)})

    if not user:
        return jsonify({"error": "User not found"}), 404

    # Convertire ObjectId in stringa per la serializzazione JSON
    user['_id'] = str(user['_id'])

    return jsonify(user), 200


@server.route('/user/delete', methods=['DELETE'])
@token_required
def delete_user():
    try:
        user_id = g.current_user.get('user_id')
        object_id = ObjectId(user_id)

        # Trova l'utente con l'ID specificato
        user = collection_user.find_one({"_id": object_id})

        if not user:
            return jsonify({"errore": "User not found"}), 404

        # Trova tutte le sessioni dell'utente
        sessions = list(collection_session.find({"user_id": str(object_id)}))

        for session in sessions:
            session_id = session["_id"]

            # Elimina tutti i samples collegati alla sessione
            collection_sensor.delete_many({"session_id": str(session_id)})

        # Elimina tutte le sessioni dell'utente
        collection_session.delete_many({"user_id": str(object_id)})

        # Elimina l'utente
        result = collection_user.delete_one({"_id": object_id})

        if result.deleted_count > 0:
            return jsonify({"messaggio": "User correctly deleted"}), 200
        else:
            return jsonify({"errore": "Errore"}), 500

    except Exception as e:
        return jsonify({"errorre": str(e)}), 500


@server.route('/user/style_average', methods=['GET'])
@token_required
def get_style_average():
    try:
        user_id = g.current_user.get('user_id')
        object_id = ObjectId(user_id)

        # Verifica se l'ID è un ObjectId valido
        if not ObjectId.is_valid(object_id):
            return jsonify({"error": "Invalid ObjectId format"}), 400


        # Trova l'utente con l'ID specificato
        user = collection_user.find_one({"_id": object_id})

        if not user:
            return jsonify({"error": "User not found"}), 404

        # Trova tutte le sessioni dell'utente
        sessions = list(collection_session.find({"user_id": str(object_id)}))

        if not sessions:
            return jsonify({"error": "No sessions found for this user"}), 404

        session_ids = [str(session['_id']) for session in sessions]

        # Trova tutti i campioni associati alle sessioni dell'utente
        samples = list(collection_sensor.find({"session_id": {"$in": session_ids}}))

        if not samples:
            return jsonify({"error": "No samples found for this user's sessions"}), 404

        # Calcola la media degli style
        total_style = 0
        count = 0

        for sample in samples:
            if 'style' in sample and sample['style'] is not None:
                total_style += sample['style']
                count += 1

        if count == 0:
            return jsonify({"error": "No valid style data found"}), 404

        style_average = total_style / count

        return jsonify({"style_average": style_average}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@server.route('/user/get_global_statistics', methods=['GET'])
@token_required
def getGlobalUserStats():
    user_id = g.current_user.get('user_id')
    user_object_id = ObjectId(user_id)

    # Trova tutte le sessioni associate all'utente
    sessions = list(collection_session.find({'user_id': str(user_object_id)}))

    # Inizializza variabili per il calcolo delle statistiche
    total_speed = 0
    total_acceleration = 0
    max_speed = 0
    max_acceleration = 0
    sample_count = 0

    # Itera attraverso tutte le sessioni e i relativi campioni
    for session in sessions:
        session_id = session['_id']
        #session_object_id = ObjectId(session_id)
        samples = list(collection_sensor.find({'session_id': str(session_id)}))

        for sample in samples:
            speed = sample['speed']
            total_acceleration_value = sample['total_acceleration']

            total_speed += speed
            total_acceleration += total_acceleration_value

            if speed > max_speed:
                max_speed = speed

            if total_acceleration_value > max_acceleration:
                max_acceleration = total_acceleration_value

            sample_count += 1

    # Calcola le statistiche medie
    if sample_count > 0:
        average_speed = total_speed / sample_count
        average_acceleration = total_acceleration / sample_count
    else:
        average_speed = 0
        average_acceleration = 0

    # Restituisci le statistiche in formato JSON
    return jsonify({
        'average_speed': average_speed,
        'average_acceleration': average_acceleration,
        'max_speed': max_speed,
        'max_acceleration': max_acceleration
    })


@server.route('/user/get_session_statistics/<session_id>', methods=['GET'])
@token_required
def getSessionMetrics(session_id):
    try:
        # Recupera tutti i campioni per la sessione data
        samples = list(collection_sensor.find({"session_id": session_id}))

        if not samples:
            return jsonify({"error": "No samples found for this session_id"}), 404

        # Calcola le metriche richieste
        total_speed = 0
        total_acceleration = 0
        max_speed = float('-inf')
        max_acceleration = float('-inf')

        for sample in samples:
            speed = sample["speed"]
            total_acceleration_value = sample["total_acceleration"]

            total_speed += speed
            total_acceleration += total_acceleration_value

            if speed > max_speed:
                max_speed = speed

            if total_acceleration_value > max_acceleration:
                max_acceleration = total_acceleration_value

        avg_speed = total_speed / len(samples)
        avg_acceleration = total_acceleration / len(samples)

        metrics = {
            "average_speed": avg_speed,
            "average_acceleration": avg_acceleration,
            "max_speed": max_speed,
            "max_acceleration": max_acceleration
        }

        return jsonify(metrics)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Endpoint to upload data to the samples collection
@server.route('/upload/samples', methods=['POST'])
def upload_samples():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(file_path)
        with open(file_path, 'r') as f:
            data = json.load(f) if filename.endswith('.json') else list(csv.DictReader(f))
            for record in data:
                record = convert_oid_fields(record)
                record = convert_dates_to_strings(record)  # Convert date fields to strings
                collection_sensor.replace_one({'_id': record['_id']}, record, upsert=True)
        os.remove(file_path)
        return jsonify({"message": "File successfully uploaded"}), 200
    else:
        return jsonify({"error": "Invalid file format"}), 400

# Endpoint to upload data to the session collection
@server.route('/upload/session', methods=['POST'])
def upload_session():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(file_path)
        with open(file_path, 'r') as f:
            data = json.load(f) if filename.endswith('.json') else list(csv.DictReader(f))
            for record in data:
                record = convert_oid_fields(record)
                record = convert_dates_to_strings(record)  # Convert date fields to strings
                collection_session.replace_one({'_id': record['_id']}, record, upsert=True)
        os.remove(file_path)
        return jsonify({"message": "File successfully uploaded"}), 200
    else:
        return jsonify({"error": "Invalid file format"}), 400

# Endpoint to upload data to the test collection
@server.route('/upload/test', methods=['POST'])
def upload_test():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file_path = os.path.join(tempfile.gettempdir(), filename)
        file.save(file_path)
        with open(file_path, 'r') as f:
            data = json.load(f) if filename.endswith('.json') else list(csv.DictReader(f))
            for record in data:
                record = convert_oid_fields(record)
                record = convert_dates_to_strings(record)  # Convert date fields to strings
                collection_test.replace_one({'_id': record['_id']}, record, upsert=True)
        os.remove(file_path)
        return jsonify({"message": "File successfully uploaded"}), 200
    else:
        return jsonify({"error": "Invalid file format"}), 400

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv', 'json'}


if __name__ == "__main__":
    app.run_server(port=8000, host="0.0.0.0")