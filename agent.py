"""
agent.py — Agent de la bateria del campus (Datathon UPC Sostenible).
Aquest codi mira les properes 24 hores i calcula la puntuacio mitjana de
cada hora i en tria les millors (durant les quals carrega la bateria al maxim) i
les pitjors (durant les quals la descarrega al maxim). En cas que no sigui bona
o dolenta, no fa res.

Aquesta puntuacio es cost = preu + 3,97 · CO2
(el 3,97 converteix kg de CO2 a "euros", amb els pesos del score oficial)

Gracies a OpenCode, sabem que la bateria perd un 10% en carregar i un 10% en descarregar. Perquè un cicle 
valgui la pena, l'hora dolenta ha de ser un ~25% pitjor que la millor 
(1/0.9^2 ≈ 1,23). Si el dia és "pla" (totes les hores similars), no val la pena moure la bateria.
Final de la simulació: si queden MENYS de 24 hores de previsió, no cal planificar res més, 
i, per tant, buidem la bateria mentre quedi energia (ja que no cal considerar el dia seguent)
"""

# Definim les constants de la bateria (no poden variar)
CAPACITAT_KWH = 2000.0   # energia màxima que cap a la bateria (kWh)
POTENCIA_KW = 500.0      # màxim que podem carregar o descarregar en una hora (kW)
RENDIMENT = 0.9 ** 0.5   # rendiment de la bateria (sqrt(0.9))
MARGE = 0.001            # petit marge de seguretat!!
PES_CO2 = 3.97           # El CO2 es 3.97 vegades mes important que el preu segons els 
#calculs seguents:

# El score és 70·ΔCO2% + 30·ΔCost%. Amb el train: cost base = 939.634 €  i  CO2 base = 551.823 kg
# PES_CO2 = (70/30) · (939634/551823) = 3.97
# Així el número de cost = preu + 3.97·CO2 és el vertader cost de cada kWh.

class BatteryAgent:
    def __init__(self):
        
        self.historial = []
        #Parametres de la bateria (class):
        self.millors_per_carregar = 7     # carrega durant les N hores més barates
        self.pitjors_per_descarregar = 8  # descarrega durant les N' hores més cares
        self.soc_max = 0.97  # deixa de carregar quan la bateria està al 97%
        self.soc_min = 0.05  # deixa de descarregar quan queda al 5%
        self.marge_minim = 1.25  # l'hora dolenta ha de ser 25% pitjor que la bona

    def act(self, obs: dict) -> float:
        try:
            consigna = self._decidir(obs)   # decidim amb el rànquing de 24h
        except Exception:
            consigna = 0.0                  # davant de qualsevol error: res (per exemple NaN etc)
        # Retall final de seguretat:
        return self._seguretat(consigna, float(obs["soc_kwh"]))

    #Ara, mirem les 24 hores seguents
    def _decidir(self, obs: dict) -> float:

        preu = []
        for v in obs["preus_properes_24h"]:
            preu.append(float(v))

        co2 = []
        for v in obs["co2_properes_24h"]:
            co2.append(float(v))

        #transformem cada hora en un sol cost, com a resultat, tenim una llista de 24 costos, amb indexos iguals a l'hora.
        costos = []
        for j in range(len(preu)):
            costos.append(preu[j] + PES_CO2 * co2[j])

        # --- PAS 3: classificar les hores -----------------------------------
        # Ordenem els ÍNDEXS de les hores (0,1,2,...) de cost més baix a més alt.
        # Exemple: ranquing = [14, 13, 15, 3, ...] -> la millor hora és la 14.
        ranquing = sorted(range(len(costos)), key=lambda j: costos[j])

        millors = ranquing[:self.millors_per_carregar]        # les N més barates
        pitjors = ranquing[-self.pitjors_per_descarregar:]    # les N més cares

        ara_bona = 0 in millors       # l'hora actual és de les bones?
        ara_dolenta = 0 in pitjors    # l'hora actual és de les dolentes?

        #En cas de que la simulacio s'acabi, buidem l'energia per obtenir la maxima quantitat de punts.
        if len(preu) < 24:
            if float(obs["soc_pct"]) > self.soc_min:
                return -POTENCIA_KW        # lliurar energia mentre quedi
            return 0.0

        # Evitem els cicles que perjudiquen al total, si la diferencia entre la millor i la pitjor hora 
        # no compensa les pèrdues (pujar i baixar energia costa ~19% del total), el cicle
        # és negatiu. En dies "plans" la millor jugada és no fer res.

        if max(costos) < min(costos) * self.marge_minim:
            return 0.0

        soc = float(obs["soc_pct"]) # nivell de bateria: 0 = buida, 1 = plena, i entre mig (0, 1)

        if ara_bona and soc < self.soc_max:
            return POTENCIA_KW    # hora BONA i bateria no plena -> CARREGAR

        if ara_dolenta and soc > self.soc_min:
            return -POTENCIA_KW                  # hora DOLENTA i bateria no buida -> DESCARREGAR

        return 0.0                  # hora neutra -> repòs (retornem 0.0 ja que ha de ser float)

    
    # Aqui el simulador penalitza si demanem més del que la bateria pot fer.
    # (convertim qualsevol consigna en una 100% segura)!

    def _seguretat(self, consigna: float, soc_kwh: float) -> float:
        # Quant podem carregar? - > Si demanem p kW durant 1h, dins entren
        # p*RENDIMENT kWh. Per no desbordar:  p*RENDIMENT <= espai_lliure
        espai_lliure = CAPACITAT_KWH - soc_kwh
        max_carregar = espai_lliure / RENDIMENT - MARGE

        # Quant podem descarregar? -> Si lliurem p kW, la bateria baixa
        # p/RENDIMENT kWh. Per no fer-la negativa:  p/RENDIMENT <= soc_kwh
        max_descarregar = soc_kwh * RENDIMENT - MARGE

        # I mai més que la potència de l'inversor, ni valors negatius:
        max_carregar = max(0.0, min(POTENCIA_KW, max_carregar))
        max_descarregar = max(0.0, min(POTENCIA_KW, max_descarregar))

        # Retallem la consigna dins de l'interval segur
        # [ -max_descarregar , +max_carregar ]
        if consigna > max_carregar:
            consigna = max_carregar
        if consigna < -max_descarregar:
            consigna = -max_descarregar
        return float(consigna)