#Stili di guida:
# 1-Prudente: Chi guida con attenzione e rispetta rigorosamente le regole della strada.
# 2-Normale: Un stile di guida equilibrato, senza eccessive accelerazioni o frenate, nel rispetto delle norme di circolazione.
# 3-Sportivo: Chi guida in modo dinamico, con accelerazioni rapide e una conduzione più orientata al divertimento.
# 4-Aggressivo: Chi ha una guida intensa, con accelerazioni e decelerazioni brusche, sorpassi rischiosi e un atteggiamento competitivo sulla strada.

#Regressione logistica multinomiale

import pandas as pd
from pymongo import MongoClient

#pacchetti per fare machine learning
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split     #per la suddivisione del dataset in addestramento e test
from sklearn.preprocessing import StandardScaler        #per standardizzare le feature
from sklearn.linear_model import LogisticRegression       #per addestrare il modello
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score    #per valutare il modello

def studyOfDrivingStyles():
    # mi connetto al db e alla collection di test
    client = MongoClient('mongodb://localhost:27017/')
    db = client['SmartDrive']
    collection = db['test']

    # Recupero dei dati dalla collezione MongoDB
    cursor = collection.find()  # Recupera tutti i documenti dalla collezione
    df = pd.DataFrame(list(cursor))  # Converti i documenti in un DataFrame pandas

    #preparazione dei dati
    # Selezione delle features (X)
    X = df[['total_acceleration', 'speed']]
    # Selezione della variabile target (y)
    y = df['classification']

    # Divisione del dataset in training e test set (80%-20%)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # standardizzo le feature
    # Creazione dello scaler
    scaler = StandardScaler()
    # Adattamento dello scaler sui dati di training e trasformazione dei dati di training
    X_train = scaler.fit_transform(X_train)
    # Trasformazione dei dati di test
    X_test = scaler.transform(X_test)

    # Converti X_train e X_test in DataFrame con nomi delle colonne originali
    X_train = pd.DataFrame(X_train, columns=X.columns)
    X_test = pd.DataFrame(X_test, columns=X.columns)

    # addestramento del modello
    # Creazione del modello di Regressione Logistica Multinomiale
    model = LogisticRegression(solver='lbfgs', max_iter=1000)
    # Addestramento del modello
    model.fit(X_train, y_train)

    #valutazione del modello
    # Predizione delle etichette per i dati di test
    y_pred = model.predict(X_test)
    # Matrice di confusione
    print("Confusion Matrix:")
    print(confusion_matrix(y_test, y_pred))
    # Report di classificazione
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, zero_division=0))  # Aggiunto zero_division=0
    # Accuratezza
    print("\nAccuracy Score:")
    print(accuracy_score(y_test, y_pred))



def calculateStyle(acceleration, speed):
    # mi connetto al db e alla collection di test
    client = MongoClient('mongodb://localhost:27017/')
    db = client['SmartDrive']
    collection = db['test']

    # Recupero dei dati dalla collezione MongoDB
    cursor = collection.find()  # Recupera tutti i documenti dalla collezione
    df = pd.DataFrame(list(cursor))  # Converti i documenti in un DataFrame pandas

    #preparazione dei dati
    # Selezione delle features (X)
    X = df[['total_acceleration', 'speed']]
    # Selezione della variabile target (y)
    y = df['classification']

    # Divisione del dataset in training e test set (80%-20%)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

    # standardizzo le feature
    # Creazione dello scaler
    scaler = StandardScaler()
    # Adattamento dello scaler sui dati di training e trasformazione dei dati di training
    X_train = scaler.fit_transform(X_train)
    # Trasformazione dei dati di test
    X_test = scaler.transform(X_test)

    # Converti X_train e X_test in DataFrame con nomi delle colonne originali
    X_train = pd.DataFrame(X_train, columns=X.columns)
    X_test = pd.DataFrame(X_test, columns=X.columns)

    # addestramento del modello
    # Creazione del modello di Regressione Logistica Multinomiale
    model = LogisticRegression(solver='lbfgs', max_iter=1000)
    # Addestramento del modello
    model.fit(X_train, y_train)

    # Esempio di nuovi dati non etichettati
    X_new = pd.DataFrame({
        'total_acceleration': [acceleration],
        'speed': [speed]
    })
    # Esegui predizioni sui nuovi dati
    predictions = model.predict(X_new)
    print(predictions[0])
    return predictions[0]


calculateStyle(0,10)

studyOfDrivingStyles()
