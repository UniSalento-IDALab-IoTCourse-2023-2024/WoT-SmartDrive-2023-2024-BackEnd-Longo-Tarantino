# Questa classe implementa un modello di machine learning per l'addestramento nella rilevazione dello stile di guida

# Stili di guida:
# 1-Prudente: Chi guida con attenzione e rispetta rigorosamente le regole della strada.
# 2-Normale: Un stile di guida equilibrato, senza eccessive accelerazioni o frenate, nel rispetto delle norme di circolazione.
# 3-Sportivo: Chi guida in modo dinamico, con accelerazioni rapide e una conduzione più orientata al divertimento.
# 4-Aggressivo: Chi ha una guida intensa, con accelerazioni e decelerazioni brusche, sorpassi rischiosi e un atteggiamento competitivo sulla strada.

# È stato utilizzato un modello di Random Forest per la classificazione. La Random Forest è un metodo di machine learning
# che utilizza una combinazione di molti alberi decisionali per migliorare la precisione e controllare l'overfitting

import pymongo
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report

global forest_model
forest_model = None

def train_model_mongodb():
    # Connessione a MongoDB
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['SmartDrive']
    collection = db['test']

    # Estrazione dei dati dal database
    cursor = collection.find({})
    data = list(cursor)

    # Debugging: Print the number of records fetched
    print(f"Number of records fetched: {len(data)}")

    if len(data) == 0:
        raise ValueError("No data found in the database. Please check the data collection process.")

    # Preparazione dei dati
    X = []
    y = []

    for entry in data:
        X.append([entry['total_acceleration'], entry['speed']])  # Features: total_acceleration e speed
        y.append(entry['classification'])  # Target: classification

    # Split dei dati in set di addestramento e test
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Debugging: Print the shape of the train and test sets
    print(f"X_train shape: {len(X_train)}, {len(X_train[0]) if X_train else 0}")
    print(f"X_test shape: {len(X_test)}, {len(X_test[0]) if X_test else 0}")
    print(f"y_train shape: {len(y_train)}")
    print(f"y_test shape: {len(y_test)}")

    # Creazione del modello Random Forest
    forest_model = RandomForestClassifier(n_estimators=100, random_state=42)

    # Addestramento del modello
    forest_model.fit(X_train, y_train)

    # Valutazione del modello con cross-validation
    scores = cross_val_score(forest_model, X_train, y_train, cv=5)
    print(f'Cross-Validation Scores: {scores}')
    print(f'Mean Cross-Validation Accuracy: {scores.mean()}')

    # Predizione sui dati di test
    y_pred = forest_model.predict(X_test)

    # Valutazione delle prestazioni del modello sui dati di test
    print(classification_report(y_test, y_pred))

    # Ritorna il modello addestrato
    return forest_model

def calculateStyle(acceleration, speed):
    # Connessione a MongoDB
    client = pymongo.MongoClient('mongodb://localhost:27017/')
    db = client['SmartDrive']
    collection = db['test']

    # Estrazione dei dati dal database
    cursor = collection.find({})
    data = list(cursor)

    # Debugging: Print the number of records fetched
    print(f"Number of records fetched: {len(data)}")

    if len(data) == 0:
        raise ValueError("No data found in the database. Please check the data collection process.")

    # Preparazione dei dati
    X = []
    y = []

    for entry in data:
        X.append([entry['total_acceleration'], entry['speed']])  # Features: total_acceleration e speed
        y.append(entry['classification'])  # Target: classification

    # Split dei dati in set di addestramento e test
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # Debugging: Print the shape of the train and test sets
    print(f"X_train shape: {len(X_train)}, {len(X_train[0]) if X_train else 0}")
    print(f"X_test shape: {len(X_test)}, {len(X_test[0]) if X_test else 0}")
    print(f"y_train shape: {len(y_train)}")
    print(f"y_test shape: {len(y_test)}")

    # Creazione del modello Random Forest
    forest_model = RandomForestClassifier(n_estimators=100, random_state=42)

    # Addestramento del modello
    forest_model.fit(X_train, y_train)

    # Test con nuovi dati
    new_data = [[acceleration, speed]]
    prediction = forest_model.predict(new_data)
    return prediction[0]

train_model_mongodb()