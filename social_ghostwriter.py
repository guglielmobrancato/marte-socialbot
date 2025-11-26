import os
import datetime
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
import google.generativeai as genai

# CONFIGURAZIONE
GENAI_API_KEY = os.environ["GEMINI_API_KEY"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
TARGET_EMAIL = os.environ["TARGET_EMAIL"]

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

def get_gemini_copy(prompt, context=""):
    full_prompt = f"""
    Sei un Social Media Manager esperto per LinkedIn. 
    Scrivi un post accattivante, professionale ma con personalità.
    Usa elenchi puntati se serve. Usa emoji pertinenti.
    Includi 3-5 hashtag strategici alla fine.
    
    CONTESTO DA ELABORARE:
    {context}
    
    RICHIESTA SPECIFICA:
    {prompt}
    """
    response = model.generate_content(full_prompt)
    return response.text

def scrape_site(url, selector):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        element = soup.select_one(selector)
        return element.text.strip() if element else "Contenuto non trovato."
    except:
        return "Errore nel leggere il sito."

def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TARGET_EMAIL
    msg['Subject'] = f"🚀 BOZZA LINKEDIN: {subject}"
    
    msg.attach(MIMEText(body, 'plain'))
    
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASSWORD)
    text = msg.as_string()
    server.sendmail(EMAIL_USER, TARGET_EMAIL, text)
    server.quit()
    print("📧 Email inviata correttamente.")

def main():
    today = datetime.datetime.now()
    weekday = today.weekday() # 0=Lun, 2=Mer, 4=Ven
    day_num = today.day

    post_type = None
    context_data = ""
    prompt = ""

    # --- LOGICA SETTIMANALE ---
    
    # LUNEDÌ: Cinema (Velvet)
    if weekday == 0:
        post_type = "Recensione Film Cult"
        # Prende il contenuto dal box vintage di Velvet Cinema
        context_data = scrape_site("https://velvet.martestudios.com/cinema.html", "#vintage-feed")
        prompt = "Scrivi un post LinkedIn per consigliare questo film cult della settimana. Parla di cinema d'autore, riscoperta e cultura visiva."

    # MERCOLEDÌ: Geopolitica (MSH)
    elif weekday == 2:
        post_type = "Intelligence Insight"
        # Prende il primo articolo di MSH (devi assicurarti che MSH abbia selettori, o usiamo un prompt generico sul sito)
        # Nota: Qui simuliamo la lettura del titolo news principale se MSH ha una struttura leggibile, 
        # altrimenti chiediamo a Gemini di generare un pensiero geopolitico basato sull'attualità.
        # Per semplicità, facciamo generare un pensiero basato sull'attualità generale se lo scraping è complesso.
        context_data = "Analisi settimanale intelligence."
        prompt = "Scrivi un post LinkedIn professionale sull'importanza di comprendere la geopolitica oggi per il business. Cita MSH (msh.martestudios.com) come fonte di intelligence affidabile."

    # VENERDÌ: Musica (Velvet)
    elif weekday == 4:
        post_type = "Album Vintage Weekend"
        context_data = scrape_site("https://velvet.martestudios.com/musica.html", "#vintage-feed")
        prompt = "Scrivi un post LinkedIn leggero per il venerdì. Consiglia questo album vintage per il weekend. Parla di creatività, ispirazione e sound design."

    # --- LOGICA MENSILE (Sovrascrive la settimanale se coincide, o si aggiunge) ---
    
    # Giorno 1: Agency
    if day_num == 1:
        post_type = "Promo Agency"
        context_data = "Servizi: Sviluppo Web App, Siti Web, Marketing Strategy."
        prompt = "Scrivi un post promozionale per 'Marte Agency' (agency.martestudios.com). Focus: Trasformiamo idee in ecosistemi digitali. Call to action per contattarci."

    # Giorno 10: Film Distribution
    elif day_num == 10:
        post_type = "Ricerca Film"
        context_data = "Cerchiamo film indipendenti per distribuzione digital e home video."
        prompt = "Scrivi un post rivolto a registi e produttori indipendenti. Marte Studios cerca nuove opere per la distribuzione. Focus su valorizzazione del talento."

    # Giorno 20: MSH Blog Promo
    elif day_num == 20:
        post_type = "Promo MSH Blog"
        context_data = "Blog di Intelligence e News Geopolitiche."
        prompt = "Scrivi un post che invita a leggere MSH (msh.martestudios.com). Focus: In un mondo caotico, l'informazione verificata è potere."

    # --- ESECUZIONE ---
    if post_type:
        print(f"Generazione post: {post_type}")
        linkedin_copy = get_gemini_copy(prompt, context_data)
        
        email_body = f"""
        Ciao! Ecco la tua bozza per LinkedIn di oggi ({post_type}).
        
        --------------------------------------------------
        
        {linkedin_copy}
        
        --------------------------------------------------
        
        [Immagine suggerita: Screenshot dal sito o foto attinente]
        
        Buon lavoro!
        Marte Social Bot
        """
        
        send_email(post_type, email_body)
    else:
        print("Oggi nessun post in calendario.")

if __name__ == "__main__":
    main()
