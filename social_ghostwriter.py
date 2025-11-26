import os
import datetime
import smtplib
import requests
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
import google.generativeai as genai

# --- CONFIGURAZIONE ---
GENAI_API_KEY = os.environ["GEMINI_API_KEY"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
TARGET_EMAIL = os.environ["TARGET_EMAIL"]

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

def clean_copy(text):
    """Pulisce il testo solo da grassetti e corsivi markdown, salvando gli hashtag"""
    if not text: return ""
    # Rimuove solo asterischi (grassetto) e underscore (corsivo)
    text = text.replace("*", "").replace("__", "")
    # NOTA: Non rimuoviamo più il #, così gli hashtag restano!
    return text.strip()

def get_gemini_copy(prompt, context):
    full_prompt = f"""
    Sei un giornalista esperto.
    Scrivi un post LinkedIn basato su questo testo.
    
    REGOLE TASSATIVE:
    1. SCRIVI SOLO IL CORPO DEL POST. Niente "Ecco il post", niente saluti, niente titoli.
    2. Usa la TERZA PERSONA (es: "L'analisi odierna...", "Marte Studios segnala...").
    3. NIENTE EMOJI. Zero.
    4. NIENTE FORMATTAZIONE MARKDOWN (No asterischi, no grassetti).
    5. Sintesi perfetta ma accattivante.
    6. INCLUDI 3-5 HASHTAG alla fine (es: #Geopolitica #News).
    
    TESTO DA RIASSUMERE:
    {context}
    
    OBIETTIVO:
    {prompt}
    """
    try:
        response = model.generate_content(full_prompt)
        return clean_copy(response.text)
    except:
        return "Errore generazione AI."

def get_msh_data():
    """Legge direttamente il file dati di MSH"""
    url = "https://msh.martestudios.com/data.js"
    try:
        response = requests.get(url)
        text = response.text
        # Il file inizia con 'const mshData = { ...' quindi puliamo per avere solo il JSON
        json_str = text.split('const mshData =')[1].strip().rstrip(';')
        data = json.loads(json_str)
        
        # Estraiamo il contenuto dell'articolo principale (monograph)
        if 'monograph' in data and 'content' in data['monograph']:
            # Puliamo l'HTML interno all'articolo per darlo in pasto a Gemini pulito
            soup = BeautifulSoup(data['monograph']['content'], 'html.parser')
            return soup.get_text(" ", strip=True)
            
    except Exception as e:
        print(f"Errore lettura MSH: {e}")
    return ""

def scrape_velvet(url, selector):
    """Legge Velvet Cinema o Musica"""
    try:
        r = requests.get(url)
        soup = BeautifulSoup(r.text, 'html.parser')
        el = soup.select_one(selector)
        return el.get_text(" ", strip=True) if el else ""
    except:
        return ""

def send_clean_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TARGET_EMAIL
    msg['Subject'] = subject 
    
    # Corpo mail: SOLO IL COPY
    msg.attach(MIMEText(body, 'plain'))
    
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASSWORD)
    server.sendmail(EMAIL_USER, TARGET_EMAIL, msg.as_string())
    server.quit()
    print("📧 Mail inviata.")

def main():
    today = datetime.datetime.now()
    weekday = today.weekday() # 0=Lun, 2=Mer, 4=Ven
    day_num = today.day

    post_copy = ""
    subject = ""

    # --- LUNEDÌ: CINEMA (Velvet) ---
    if weekday == 0:
        raw_text = scrape_velvet("https://velvet.martestudios.com/cinema.html", "#vintage-feed")
        if raw_text:
            subject = "LinkedIn: Cinema Cult"
            post_copy = get_gemini_copy("Riassumi questa recensione film cult. Focus su regia e storia.", raw_text)

    # --- MERCOLEDÌ: MSH (Geopolitica) ---
    elif weekday == 2:
        # QUI LA MAGIA: Legge il file JS di MSH
        raw_text = get_msh_data()
        if raw_text:
            subject = "LinkedIn: MSH Geopolitica"
            post_copy = get_gemini_copy("Riassumi questa analisi di intelligence. Tono serio e analitico. Cita msh.martestudios.com", raw_text)
        else:
            post_copy = "Errore lettura dati MSH. Controllare il sito."

    # --- VENERDÌ: MUSICA (Velvet) ---
    elif weekday == 4:
        raw_text = scrape_velvet("https://velvet.martestudios.com/musica.html", "#vintage-feed")
        if raw_text:
            subject = "LinkedIn: Musica Vintage"
            post_copy = get_gemini_copy("Riassumi questa recensione album. Focus su sound e groove.", raw_text)

    # --- MENSILE (Promo) ---
    if day_num == 1:
        subject = "LinkedIn: Promo Agency"
        post_copy = get_gemini_copy("Post corporate servizi web/marketing Marte Agency.", "Sviluppo Web, App, Marketing Strategy.")
    elif day_num == 10:
        subject = "LinkedIn: Call Movies"
        post_copy = get_gemini_copy("Call to action per registi indipendenti. Distribuzione film.", "Cerchiamo opere da distribuire.")
    elif day_num == 20:
        subject = "LinkedIn: Promo MSH"
        post_copy = get_gemini_copy("Invito a leggere MSH per news verificate.", "MSH: Intelligence & News.")

    # --- INVIO ---
    if post_copy and subject:
        print(f"Invio mail per: {subject}")
        send_clean_email(subject, post_copy)
    else:
        print("Nessun post oggi o errore lettura dati.")

if __name__ == "__main__":
    main()
