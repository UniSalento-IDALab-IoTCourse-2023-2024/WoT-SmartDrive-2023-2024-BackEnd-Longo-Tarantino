import numpy as np
from math import atan2, asin, pi
import hashlib

# questo metodo permette di calcolare il rollio e il beccheggio dei nostri campioni
def madgwick_filter(ax, ay, az, gx, gy, gz, dt):
    # Converti le letture dell'accelerometro in radianti. Quando il dispositivo è stazionario e fermo rispetto alla gravità, l'unico componente dell'accelerazione che influenzerà i calcoli di orientamento sono quelli lungo gli assi axax e ayay
    ax_rad = atan2(ay, az)
    ay_rad = atan2(-ax, np.sqrt(ay**2 + az**2))

    # Misure del giroscopio in radianti per secondo
    gx_rad = gx * (pi / 180.0)
    gy_rad = gy * (pi / 180.0)
    gz_rad = gz * (pi / 180.0)

    # Algoritmo del filtro di Madgwick
    q0, q1, q2, q3 = 1.0, 0.0, 0.0, 0.0  # Elementi del quaternione rappresentanti l'orientamento
    beta = 0.1  # Guadagno dell'algoritmo

    q0 += (-q1 * gx_rad - q2 * gy_rad - q3 * gz_rad) * (0.5 * dt)
    q1 += (q0 * gx_rad + q2 * gz_rad - q3 * gy_rad) * (0.5 * dt)
    q2 += (q0 * gy_rad - q1 * gz_rad + q3 * gx_rad) * (0.5 * dt)
    q3 += (q0 * gz_rad + q1 * gy_rad - q2 * gx_rad) * (0.5 * dt)

    # Normalizza il quaternione
    norm = np.sqrt(q0**2 + q1**2 + q2**2 + q3**2)
    q0 /= norm
    q1 /= norm
    q2 /= norm
    q3 /= norm

    # Calcola gli angoli di beccheggio e rollio
    pitch = asin(-2.0 * (q1 * q3 - q0 * q2))
    roll = atan2(2.0 * (q0 * q1 + q2 * q3), 1.0 - 2.0 * (q1**2 + q2**2))

    #print(f'rollio {roll}')
    #print(f'beccheggio {pitch}')

    return roll, pitch




# Funzione per fare l'hash delle pass
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()