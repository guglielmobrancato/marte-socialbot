import os
import datetime
import smtplib
import requests
import re
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

def clean_text(text):
    """Pulisce il testo da formattazione markdown indesiderata"""
    if not text: return ""
    text = text.replace("*", "") 
    text = text.replace("#", "")
    return text

def get_gemini_copy(prompt, context="", link_url=""):
    full_prompt = f"""
    Sei un giornalista senior per LinkedIn.
    
    OBIETTIVO:
    Scrivi un post LinkedIn basato ESCLUSIVAMENTE sul testo fornito nel contesto.
    
    REGOLE DI STILE INDEROGABILI:
    1. Scrivi in TERZA PERSONA (es: "L'analisi di oggi...", "Il report evidenzia...").
    2. NIENTE EMOJI. Zero.
    3. NIENTE ASTERISCHI o formattazione markdown.
    4. Stile: Professionale, sintetico, giornalistico.
    5. NON INVENTARE: Riassumi solo quello che leggi nel contesto.
    
    STRUTTURA:
    - Frase gancio (senza titolo).
    - Riassunto del contenuto (2-3 frasi dense).
    - Conclusione.
    - Link: {link_url}
    - 3 Hashtag finali.

    CONTESTO DA RIASSUMERE:
    {context}
    
    ISTRUZIONE SPECIFICA:
    {prompt}
    """
    response = model.generate_content(full_prompt)
    return clean_text(response.text)

def scrape_section(url, selector):
    """Scarica SOLO il testo della sezione"""
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        element = soup.select_one(selector)
        if element:
            return element.get_text(separator=" ", strip=True)[:2000]
    except Exception as e:
        print(f"Errore scraping {url}: {e}")
    return "Contenuto non disponibile."

def send_email(subject, body):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TARGET_EMAIL
    msg['Subject'] = f"📄 POST LINKEDIN: {subject}"
    msg.attach(MIMEText(body, 'plain'))
    
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASSWORD)
    text = msg.as_string()
    server.sendmail(EMAIL_USER, TARGET_EMAIL, text)
    server.quit()
    print("📧 Email inviata.")

def main():
    today = datetime.datetime.now()
    weekday = today.weekday() # 0=Lun, 2=Mer, 4=Ven
    day_num = today.day

    post_type = None
    prompt = ""
    link_url = ""
    scraped_text = ""

    # --- SETTIMANALE ---
    
    # LUNEDÌ: Cinema (Pellicola Cult)
    if weekday == 0:
        post_type = "Cinema Cult Week"
        link_url = "https://velvet.martestudios.com/cinema.html"
        scraped_text = scrape_section(link_url, "#vintage-feed")
        prompt = "Riassumi questa recensione di un film cult. Parla dell'importanza di riscoprire il cinema del passato."

    # MERCOLEDÌ: MSH (Recap Geopolitica del Giorno)
    elif weekday == 2:
        post_type = "MSH Intelligence Recap"
        link_url = "https://msh.martestudios.com"
        # Prende il primo articolo disponibile
        scraped_text = scrape_section(link_url, "article") 
        if len(scraped_text) < 50: # Fallback se non trova 'article'
             scraped_text = scrape_section(link_url, "body")
        prompt = "Riassumi questo articolo di geopolitica. Metti in luce i punti chiave dell'analisi odierna."

    # VENERDÌ: Musica (Album Vintage)
    elif weekday == 4:
        post_type = "Music Vinyl Friday"
        link_url = "https://velvet.martestudios.com/musica.html"
        scraped_text = scrape_section(link_url, "#vintage-feed")
        prompt = "Riassumi questa recensione di un album vintage. Parla di groove e sonorità."

    # --- MENSILE (Promo) ---
    
    if day_num == 1:
        post_type = "Promo Agency"
        link_url = "https://agency.martestudios.com"
        scraped_text = "Servizi: Sviluppo Web, App, Marketing Strategy."
        prompt = "Scrivi un post corporate sui servizi di Marte Agency."

    elif day_num == 10:
        post_type = "Call for Movies"
        link_url = "https://martestudios.com"
        scraped_text = "Call per registi indipendenti: Distribuzione digital e home video."
        prompt = "Scrivi una call-to-action per registi. Cerchiamo opere da distribuire."

    elif day_num == 20:
        post_type = "Promo MSH Blog"
        link_url = "https://msh.martestudios.com"
        scraped_text = "MSH: Intelligence & Geopolitical News."
        prompt = "Invita a leggere MSH per analisi globali verificate."

    # --- INVIO ---
    if post_type:
        print(f"Generazione post: {post_type}")
        
        # Genera il copy
        linkedin_copy = get_gemini_copy(prompt, scraped_text, link_url)

        email_body = f"""
        POST LINKEDIN ({post_type})
        
        1. Copia il testo.
        2. Pubblica su LinkedIn (allega tu un'immagine se vuoi).
        
        --- COPY ---
        
        {linkedin_copy}
        
        --- FINE ---
        """
        
        send_email(post_type, email_body)
    else:
        print("Nessun post oggi.")

if __name__ == "__main__":
    main()
