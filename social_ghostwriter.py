import os
import datetime
import smtplib
import requests
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
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
    
    IL TUO OBIETTIVO:
    Scrivi un post LinkedIn basato ESCLUSIVAMENTE sul testo fornito nel contesto.
    
    REGOLE DI STILE INDEROGABILI:
    1. Scrivi in TERZA PERSONA (es: "L'analisi di oggi...", "Il report evidenzia...").
    2. NIENTE EMOJI. Zero. Nemmeno una.
    3. NIENTE ASTERISCHI o formattazione markdown.
    4. Stile: Professionale, sintetico, 'catchy' ma serio.
    5. NON INVENTARE: Riassumi solo quello che leggi nel contesto.
    
    STRUTTURA:
    - Titolo/Gancio (senza scriverlo come titolo, solo una frase forte).
    - Riassunto del contenuto (2-3 frasi).
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
    """Scarica il testo specifico di una sezione"""
    data = {"text": "", "img_url": None}
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Cerca l'elemento specifico
        element = soup.select_one(selector)
        
        if element:
            # Pulisce il testo
            data["text"] = element.get_text(separator=" ", strip=True)[:2000]
            
            # Cerca immagine dentro l'elemento o nei paraggi
            img = element.find('img')
            if img and img.has_attr('src'):
                src = img['src']
                if not src.startswith('http'): src = url + src
                data["img_url"] = src
                
        return data
    except Exception as e:
        print(f"Errore scraping {url}: {e}")
        return data

def download_image(url):
    try:
        if not url: return None
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            return response.content
    except:
        pass
    return None

def send_email(subject, body, image_data):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TARGET_EMAIL
    msg['Subject'] = f"📄 POST LINKEDIN: {subject}"
    msg.attach(MIMEText(body, 'plain'))
    
    if image_data:
        image = MIMEImage(image_data, name="social_image.jpg")
        msg.attach(image)
    
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
    scraped_data = {"text": "", "img_url": None}

    # --- SETTIMANALE ---
    
    # LUNEDÌ: Cinema (Pellicola Cult)
    if weekday == 0:
        post_type = "Cinema Cult Week"
        link_url = "https://velvet.martestudios.com/cinema.html"
        # PRENDE SOLO IL CONTENUTO DEL BOX VINTAGE (#vintage-feed)
        scraped_data = scrape_section(link_url, "#vintage-feed")
        # Se non c'è img nel box, ne mettiamo una generica cinema
        if not scraped_data["img_url"]: 
             scraped_data["img_url"] = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?q=80&w=1080"
        prompt = "Riassumi questa recensione di un film cult. Parla dell'importanza di riscoprire il cinema del passato."

    # MERCOLEDÌ: MSH (Recap Geopolitica del Giorno)
    elif weekday == 2:
        post_type = "MSH Intelligence Recap"
        link_url = "https://msh.martestudios.com"
        # PRENDE IL PRIMO ARTICOLO IN ALTO (che è il recap IA giornaliero)
        # Nota: Usiamo "article" come selettore generico, o il container specifico delle news se diverso.
        scraped_data = scrape_section(link_url, "article") 
        
        # Immagine generica news se non trovata
        if not scraped_data["img_url"]:
            scraped_data["img_url"] = "https://images.unsplash.com/photo-1504711434969-e33886168f5c?q=80&w=1080"
            
        prompt = "Riassumi questo articolo di geopolitica. Metti in luce i punti chiave dell'analisi odierna."

    # VENERDÌ: Musica (Album Vintage)
    elif weekday == 4:
        post_type = "Music Vinyl Friday"
        link_url = "https://velvet.martestudios.com/musica.html"
        # PRENDE SOLO IL CONTENUTO DEL BOX VINTAGE (#vintage-feed)
        scraped_data = scrape_section(link_url, "#vintage-feed")
        # Immagine vinile generica
        scraped_data["img_url"] = "https://images.unsplash.com/photo-1614613535308-eb5fbd3d2c17?q=80&w=1080"
        prompt = "Riassumi questa recensione di un album vintage. Parla di groove e sonorità."

    # --- MENSILE (Promo) ---
    
    if day_num == 1:
        post_type = "Promo Agency"
        link_url = "https://agency.martestudios.com"
        scraped_data["text"] = "Servizi: Sviluppo Web, App, Marketing Strategy."
        scraped_data["img_url"] = "https://images.unsplash.com/photo-1522071820081-009f0129c71c?q=80&w=1080"
        prompt = "Scrivi un post corporate sui servizi di Marte Agency."

    elif day_num == 10:
        post_type = "Call for Movies"
        link_url = "https://martestudios.com"
        scraped_data["text"] = "Call per registi indipendenti: Distribuzione digital e home video."
        scraped_data["img_url"] = "https://images.unsplash.com/photo-1485846234645-a62644f84728?q=80&w=1080"
        prompt = "Scrivi una call-to-action per registi. Cerchiamo opere da distribuire."

    elif day_num == 20:
        post_type = "Promo MSH Blog"
        link_url = "https://msh.martestudios.com"
        scraped_data["text"] = "MSH: Intelligence & Geopolitical News."
        scraped_data["img_url"] = "https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=1080"
        prompt = "Invita a leggere MSH per analisi globali verificate."

    # --- INVIO ---
    if post_type:
        print(f"Generazione post: {post_type}")
        
        # Se non abbiamo trovato testo nel sito (errore scraping), usiamo un fallback
        if len(scraped_data["text"]) < 20:
            scraped_data["text"] = "Contenuto attualmente non disponibile. Invitare a visitare il sito."
            
        linkedin_copy = get_gemini_copy(prompt, scraped_data["text"], link_url)
        image_bytes = download_image(scraped_data["img_url"])

        email_body = f"""
        POST LINKEDIN ({post_type})
        
        1. Scarica immagine allegata.
        2. Copia testo.
        3. Pubblica.
        
        --- COPY ---
        {linkedin_copy}
        --- FINE ---
        """
        
        send_email(post_type, email_body, image_bytes)
    else:
        print("Nessun post oggi.")

if __name__ == "__main__":
    main()
