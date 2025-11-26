import os
import datetime
import smtplib
import requests
import io
import re
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

# --- FONT URLS (Con User-Agent per evitare blocchi) ---
FONTS = {
    'cinema': 'https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf',
    'intelligence': 'https://github.com/google/fonts/raw/main/ofl/playfairdisplay/PlayfairDisplay-Bold.ttf',
    'music': 'https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf',
    'agency': 'https://github.com/google/fonts/raw/main/apache/robotoslab/RobotoSlab-Bold.ttf'
}

def download_font(url):
    try:
        # Alcuni server bloccano richieste senza User-Agent
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return io.BytesIO(r.content)
    except Exception as e:
        print(f"Errore Font {url}: {e}")
    return None

def wrap_text(text, font, max_width, draw):
    if not text: return []
    lines = []
    words = text.split(' ')
    current_line = []
    for word in words:
        current_line.append(word)
        # Rimuove asterischi per calcolare la larghezza reale
        test_line = ' '.join(current_line).replace('*', '')
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w > max_width:
            current_line.pop()
            lines.append(' '.join(current_line))
            current_line = [word]
    lines.append(' '.join(current_line))
    return lines

def create_slide(title, text, footer, font_url, is_cover=False):
    W, H = 1080, 1080
    img = Image.new('RGB', (W, H), color='#050202')
    draw = ImageDraw.Draw(img)
    
    font_bytes = download_font(font_url)
    
    # Fallback dimensioni se il font non carica
    size_title = 110 if is_cover else 60
    size_body = 48
    size_footer = 28
    
    try:
        if font_bytes:
            font_title = ImageFont.truetype(font_bytes, size_title)
            font_bytes.seek(0)
            font_body = ImageFont.truetype(font_bytes, size_body)
            font_bytes.seek(0)
            font_footer = ImageFont.truetype(font_bytes, size_footer)
        else:
            raise Exception("Font non scaricato")
    except:
        print("Usando font default (brutto ma leggibile)")
        font_title = font_body = font_footer = ImageFont.load_default()

    # Colori
    COL_ORANGE = '#ff5500'
    COL_WHITE = '#f0f0f0'
    COL_GREY = '#aaaaaa'

    # Header
    draw.text((80, 80), str(title).upper(), font=font_title, fill=COL_ORANGE)
    draw.line((80, 80 + size_title + 25, W-80, 80 + size_title + 25), fill=COL_ORANGE, width=3)

    # Corpo (Se vuoto, scrive un placeholder per debug)
    if not text or len(text) < 2: text = "Contenuto mancante."
    
    start_y = 360
    max_w = W - 160
    lines = wrap_text(str(text), font_body, max_w, draw)
    current_y = start_y
    
    for line in lines:
        parts = line.split('*')
        current_x = 80
        for i, part in enumerate(parts):
            color = COL_ORANGE if i % 2 != 0 else COL_WHITE
            if not part: continue
            draw.text((current_x, current_y), part, font=font_body, fill=color)
            bbox = draw.textbbox((0, 0), part, font=font_body)
            current_x += (bbox[2] - bbox[0])
        current_y += size_body + 15

    draw.text((80, H-80), str(footer), font=font_footer, fill=COL_GREY)
    return img

def get_gemini_content(prompt, context):
    full_prompt = f"""
    Sei un Social Media Manager.
    CONTESTO: {context}
    
    Compito: Scrivi il copy per LinkedIn e 4 slide brevi.
    IMPORTANTE: Metti le parole chiave delle slide tra asterischi (*).
    
    USA ESATTAMENTE QUESTI TAG PER SEPARARE LE PARTI:
    
    [[COPY_START]]
    (Qui scrivi il testo del post)
    [[COPY_END]]
    
    [[TITOLO_START]]
    (Titolo Cover)
    [[TITOLO_END]]
    
    [[SLIDE1_START]]
    (Concetto 1)
    [[SLIDE1_END]]
    
    [[SLIDE2_START]]
    (Concetto 2)
    [[SLIDE2_END]]
    
    [[SLIDE3_START]]
    (Conclusione)
    [[SLIDE3_END]]
    
    Istruzione: {prompt}
    """
    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def extract_tag(text, tag_name):
    """Estrae il testo tra [[TAG_START]] e [[TAG_END]] usando Regex"""
    pattern = f"\\[\\[{tag_name}_START\\]\\](.*?)\\[\\[{tag_name}_END\\]\\]"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return "" # Ritorna vuoto se non trova

def parse_response(text):
    data = {}
    data['copy'] = extract_tag(text, "COPY")
    data['titolo'] = extract_tag(text, "TITOLO")
    data['s1'] = extract_tag(text, "SLIDE1")
    data['s2'] = extract_tag(text, "SLIDE2")
    data['s3'] = extract_tag(text, "SLIDE3")
    
    # Fallback se l'AI fallisce i tag
    if not data['copy']: data['copy'] = "Errore generazione testo. Controllare AI."
    if not data['titolo']: data['titolo'] = "MARTE UPDATE"
    if not data['s1']: data['s1'] = "Dati non disponibili."
    
    return data

def scrape_section(url, selector):
    try:
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        el = soup.select_one(selector)
        return el.get_text(" ", strip=True)[:2000] if el else ""
    except: return ""

def send_email_kit(subject, body, images_list, pdf_bytes):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TARGET_EMAIL
    msg['Subject'] = f"📦 MEDIA KIT: {subject}"
    msg.attach(MIMEText(body, 'plain'))
    
    pdf_att = MIMEApplication(pdf_bytes, _subtype="pdf")
    pdf_att.add_header('Content-Disposition', 'attachment', filename="carosello.pdf")
    msg.attach(pdf_att)
    
    for i, img_bytes in enumerate(images_list):
        img = MIMEImage(img_bytes, name=f"slide_{i+1}.jpg")
        msg.attach(img)
        
    s = smtplib.SMTP('smtp.gmail.com', 587)
    s.starttls()
    s.login(EMAIL_USER, EMAIL_PASSWORD)
    s.sendmail(EMAIL_USER, TARGET_EMAIL, msg.as_string())
    s.quit()
    print("📧 Kit inviato.")

def main():
    today = datetime.datetime.now()
    weekday = today.weekday()
    day_num = today.day

    post_type = None; prompt = ""; font_key = 'agency'; link_url = ""; scraped_text = ""

    # --- CALENDARIO ---
    if weekday == 0: 
        post_type = "Cinema Cult"; font_key = 'cinema'
        link_url = "https://velvet.martestudios.com/cinema.html"
        scraped_text = scrape_section(link_url, "#vintage-feed")
        prompt = "Slide educative film."

    elif weekday == 2: 
        post_type = "Intelligence"; font_key = 'intelligence'
        link_url = "https://msh.martestudios.com"
        scraped_text = scrape_section(link_url, "article")
        if len(scraped_text)<20: scraped_text = scrape_section(link_url, "body")
        prompt = "Slide analitiche geopolitica."

    elif weekday == 4: 
        post_type = "Music Vibe"; font_key = 'music'
        link_url = "https://velvet.martestudios.com/musica.html"
        scraped_text = scrape_section(link_url, "#vintage-feed")
        prompt = "Slide sound album."

    # --- MENSILE ---
    if day_num == 1:
        post_type = "Promo Agency"; font_key = 'agency'
        scraped_text = "Sviluppo Web, App, Marketing."; prompt = "Slide corporate."
    elif day_num == 10:
        post_type = "Call Movies"; font_key = 'cinema'
        scraped_text = "Call registi."; prompt = "Slide per registi."
    elif day_num == 20:
        post_type = "Promo MSH"; font_key = 'intelligence'
        scraped_text = "MSH News."; prompt = "Slide importanza info."

    # --- ESECUZIONE ---
    if post_type:
        print(f"Generazione: {post_type}")
        raw = get_gemini_content(prompt, scraped_text)
        
        # Debug print (visibile nei log di GitHub se serve)
        # print(raw) 
        
        data = parse_response(raw)
        
        slides_imgs = []
        font_url = FONTS[font_key]
        footer_text = "MARTE STUDIOS"

        slides_imgs.append(create_slide(data['titolo'], "Scorri per leggere ->", footer_text, font_url, is_cover=True))
        slides_imgs.append(create_slide("INSIGHT 01", data['s1'], footer_text, font_url))
        slides_imgs.append(create_slide("INSIGHT 02", data['s2'], footer_text, font_url))
        slides_imgs.append(create_slide("CONCLUSIONE", data['s3'], footer_text, font_url))

        jpg_list = []
        for img in slides_imgs:
            buf = io.BytesIO(); img.save(buf, format='JPEG', quality=95); jpg_list.append(buf.getvalue())
        
        pdf_buf = io.BytesIO()
        slides_imgs[0].save(pdf_buf, format='PDF', save_all=True, append_images=slides_imgs[1:])
        
        email_body = f"""
        KIT COMPLETO: {post_type}
        
        --- COPY LINKEDIN ---
        
        {data['copy']}
        
        Link: {link_url}
        
        ---------------------
        In allegato: PDF per carosello + Immagini per Instagram.
        """
        
        send_email_kit(post_type, email_body, jpg_list, pdf_buf.getvalue())
    else:
        print("Nessun post oggi.")

if __name__ == "__main__":
    main()
