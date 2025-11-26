import os
import datetime
import smtplib
import requests
import io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from bs4 import BeautifulSoup
import google.generativeai as genai
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURAZIONE ---
GENAI_API_KEY = os.environ["GEMINI_API_KEY"]
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
TARGET_EMAIL = os.environ["TARGET_EMAIL"]

genai.configure(api_key=GENAI_API_KEY)
model = genai.GenerativeModel('gemini-2.0-flash')

# --- FONT URLS (Google Fonts raw) ---
FONTS = {
    'cinema': 'https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf', # Quasi Helvetica
    'intelligence': 'https://github.com/google/fonts/raw/main/ofl/playfairdisplay/PlayfairDisplay-Bold.ttf', # Elegante
    'music': 'https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf', # Poster Style
    'agency': 'https://github.com/google/fonts/raw/main/apache/robotoslab/RobotoSlab-Bold.ttf' # Tech/Corporate
}

def download_font(url):
    try:
        r = requests.get(url)
        return io.BytesIO(r.content)
    except:
        return None # Fallback al default se fallisce

def wrap_text(text, font, max_width, draw):
    """Calcola come andare a capo"""
    lines = []
    words = text.split(' ')
    current_line = []
    
    for word in words:
        current_line.append(word)
        # Calcola larghezza riga provvisoria (senza asterischi per la misura)
        test_line = ' '.join(current_line).replace('*', '')
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        
        if w > max_width:
            current_line.pop() # Rimuovi l'ultima parola che sfora
            lines.append(' '.join(current_line))
            current_line = [word] # Inizia nuova riga
            
    lines.append(' '.join(current_line))
    return lines

def create_slide(title, text, footer, font_url, is_cover=False):
    # 1. Setup Canvas (Nero Marte)
    W, H = 1080, 1080
    img = Image.new('RGB', (W, H), color='#050202')
    draw = ImageDraw.Draw(img)
    
    # 2. Carica Font
    font_bytes = download_font(font_url)
    
    # Dimensioni Font
    size_title = 120 if is_cover else 60
    size_body = 50
    size_footer = 30
    
    try:
        font_title = ImageFont.truetype(font_bytes, size_title)
        font_bytes.seek(0)
        font_body = ImageFont.truetype(font_bytes, size_body)
        font_bytes.seek(0)
        font_footer = ImageFont.truetype(font_bytes, size_footer)
    except:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()
        font_footer = ImageFont.load_default()

    # 3. Colori
    COL_ORANGE = '#ff5500'
    COL_WHITE = '#ffffff'
    COL_GREY = '#a0a0a0'

    # 4. Disegna Header/Titolo
    draw.text((80, 80), title.upper(), font=font_title, fill=COL_ORANGE)
    
    # Linea divisoria
    draw.line((80, 80 + size_title + 20, W-80, 80 + size_title + 20), fill='#333', width=5)

    # 5. Disegna Corpo del testo (con gestione grassetto/colore)
    start_y = 350
    max_w = W - 160
    
    lines = wrap_text(text, font_body, max_w, draw)
    
    current_y = start_y
    for line in lines:
        # Logica per evidenziare le parole tra asterischi *parola*
        parts = line.split('*')
        current_x = 80
        
        for i, part in enumerate(parts):
            # Se i è dispari, era tra asterischi -> ARANCIONE
            color = COL_ORANGE if i % 2 != 0 else COL_WHITE
            
            if not part: continue
            
            draw.text((current_x, current_y), part, font=font_body, fill=color)
            
            # Avanza cursore X
            bbox = draw.textbbox((0, 0), part, font=font_body)
            part_w = bbox[2] - bbox[0]
            current_x += part_w
        
        current_y += size_body + 20 # Interlinea

    # 6. Footer
    draw.text((80, H-100), footer, font=font_footer, fill=COL_GREY)
    
    return img

def get_gemini_content(prompt, context):
    full_prompt = f"""
    Sei un Social Media Manager.
    
    CONTESTO: {context}
    
    OBIETTIVO 1: Scrivi il copy LinkedIn (Terza persona, No Emoji).
    OBIETTIVO 2: Scrivi i testi per 4 Slide.
    
    IMPORTANTE: Metti le PAROLE CHIAVE delle slide tra asterischi (es: *Concetto Chiave*). 
    Il sistema le colorerà in arancione.
    
    FORMATO OUTPUT:
    ---COPY---
    (Testo post)
    ---SLIDE_TITOLO---
    (Titolo Cover, max 5 parole)
    ---SLIDE_1---
    (Concetto 1, usa *asterischi* per enfasi)
    ---SLIDE_2---
    (Concetto 2, usa *asterischi* per enfasi)
    ---SLIDE_3---
    (Conclusione, usa *asterischi* per enfasi)
    ---FINE---
    
    ISTRUZIONE: {prompt}
    """
    response = model.generate_content(full_prompt)
    return response.text

def parse_response(text):
    data = {'copy': '', 'titolo': 'Marte Update', 's1': '...', 's2': '...', 's3': '...'}
    parts = text.split('---')
    for p in parts:
        if p.startswith('COPY'): data['copy'] = p.replace('COPY', '').strip()
        elif p.startswith('SLIDE_TITOLO'): data['titolo'] = p.replace('SLIDE_TITOLO', '').strip()
        elif p.startswith('SLIDE_1'): data['s1'] = p.replace('SLIDE_1', '').strip()
        elif p.startswith('SLIDE_2'): data['s2'] = p.replace('SLIDE_2', '').strip()
        elif p.startswith('SLIDE_3'): data['s3'] = p.replace('SLIDE_3', '').strip()
    return data

def scrape_section(url, selector):
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, 'html.parser')
        el = soup.select_one(selector)
        return el.get_text(separator=" ", strip=True)[:2000] if el else ""
    except: return ""

def send_email_kit(subject, body, images_list, pdf_bytes):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TARGET_EMAIL
    msg['Subject'] = f"📦 MEDIA KIT: {subject}"
    msg.attach(MIMEText(body, 'plain'))
    
    # Allega PDF
    pdf_att = MIMEApplication(pdf_bytes, _subtype="pdf")
    pdf_att.add_header('Content-Disposition', 'attachment', filename="carosello.pdf")
    msg.attach(pdf_att)
    
    # Allega JPG (per Instagram)
    for i, img_bytes in enumerate(images_list):
        img = MIMEImage(img_bytes, name=f"slide_{i+1}.jpg")
        msg.attach(img)
        
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_USER, EMAIL_PASSWORD)
    text = msg.as_string()
    server.sendmail(EMAIL_USER, TARGET_EMAIL, text)
    server.quit()
    print("📧 Kit inviato.")

def main():
    today = datetime.datetime.now()
    weekday = today.weekday()
    day_num = today.day

    post_type = None
    prompt = ""
    font_key = 'agency' # Default
    link_url = ""
    scraped_text = ""

    # --- CALENDARIO ---
    if weekday == 0: # Lun
        post_type = "Cinema Cult"
        font_key = 'cinema'
        link_url = "https://velvet.martestudios.com/cinema.html"
        scraped_text = scrape_section(link_url, "#vintage-feed")
        prompt = "Slide educative sul film. Focus registico."

    elif weekday == 2: # Mer
        post_type = "Intelligence"
        font_key = 'intelligence'
        link_url = "https://msh.martestudios.com"
        scraped_text = scrape_section(link_url, "article")
        if len(scraped_text)<20: scraped_text = scrape_section(link_url, "body")
        prompt = "Slide analitiche. Punti geopolitici chiave."

    elif weekday == 4: # Ven
        post_type = "Music Vibe"
        font_key = 'music'
        link_url = "https://velvet.martestudios.com/musica.html"
        scraped_text = scrape_section(link_url, "#vintage-feed")
        prompt = "Slide sul sound e l'album. Stile groovy."

    # --- MENSILE ---
    if day_num == 1:
        post_type = "Promo Agency"
        font_key = 'agency'
        link_url = "https://agency.martestudios.com"
        scraped_text = "Sviluppo Web, App, Marketing."
        prompt = "Slide corporate sui servizi."

    elif day_num == 10:
        post_type = "Call for Movies"
        font_key = 'cinema'
        scraped_text = "Call per registi."
        prompt = "Slide per attrarre registi."

    elif day_num == 20:
        post_type = "Promo MSH"
        font_key = 'intelligence'
        scraped_text = "MSH News."
        prompt = "Slide sull'importanza dell'info."

    # --- ESECUZIONE ---
    if post_type:
        print(f"Generazione: {post_type} (Font: {font_key})")
        raw = get_gemini_content(prompt, scraped_text)
        data = parse_response(raw)
        
        # Generazione Immagini (Pillow)
        slides_imgs = []
        font_url = FONTS[font_key]
        
        # Slide 1: Cover
        slides
