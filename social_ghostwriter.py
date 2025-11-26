import os
import datetime
import smtplib
import requests
import io
import time
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

# --- FONT URLS ---
FONTS = {
    'cinema': 'https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf',
    'intelligence': 'https://github.com/google/fonts/raw/main/ofl/playfairdisplay/PlayfairDisplay-Bold.ttf',
    'music': 'https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf',
    'agency': 'https://github.com/google/fonts/raw/main/apache/robotoslab/RobotoSlab-Bold.ttf'
}

def download_font(url):
    try:
        r = requests.get(url, timeout=10)
        return io.BytesIO(r.content)
    except: return None

def wrap_text(text, font, max_width, draw):
    lines = []
    words = text.split(' ')
    current_line = []
    for word in words:
        current_line.append(word)
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
    
    # SFONDO GENERATO VIA CODICE (Nero Marte)
    # Non cerca file esterni, quindi non può crashare
    img = Image.new('RGB', (W, H), color='#050202')
    draw = ImageDraw.Draw(img)
    
    # Carica Font
    font_bytes = download_font(font_url)
    size_title = 110 if is_cover else 60
    size_body = 48
    size_footer = 28
    
    try:
        font_title = ImageFont.truetype(font_bytes, size_title)
        font_bytes.seek(0)
        font_body = ImageFont.truetype(font_bytes, size_body)
        font_bytes.seek(0)
        font_footer = ImageFont.truetype(font_bytes, size_footer)
    except:
        font_title = font_body = font_footer = ImageFont.load_default()

    # Colori
    COL_ORANGE = '#ff5500'
    COL_WHITE = '#f0f0f0'
    COL_GREY = '#aaaaaa'

    # Disegna
    draw.text((80, 80), title.upper(), font=font_title, fill=COL_ORANGE)
    draw.line((80, 80 + size_title + 25, W-80, 80 + size_title + 25), fill=COL_ORANGE, width=3)

    start_y = 360
    max_w = W - 160
    lines = wrap_text(text, font_body, max_w, draw)
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

    draw.text((80, H-80), footer, font=font_footer, fill=COL_GREY)
    return img

def get_gemini_content(prompt, context):
    full_prompt = f"""
    Sei un Social Media Manager. CONTESTO: {context}
    OBIETTIVO 1: Copy LinkedIn (Terza persona, No Emoji).
    OBIETTIVO 2: 4 Slide brevi.
    IMPORTANTE: Metti le *PAROLE CHIAVE* delle slide tra asterischi.
    FORMATO OUTPUT:
    ---COPY--- (Testo)
    ---SLIDE_TITOLO--- (Titolo)
    ---SLIDE_1--- (Concetto 1)
    ---SLIDE_2--- (Concetto 2)
    ---SLIDE_3--- (Conclusione)
    Istruzione: {prompt}
    """
    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"Errore Gemini: {e}"

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
        data = parse_response(raw)
        
        slides_imgs = []
        font_url = FONTS[font_key]
        footer_text = f"MARTE STUDIOS | {link_url.replace('https://','')}"

        slides_imgs.append(create_slide(data['titolo'], "Scorri per leggere ->", footer_text, font_url, is_cover=True))
        slides_imgs.append(create_slide("INSIGHT 01", data['s1'], footer_text, font_url))
        slides_imgs.append(create_slide("INSIGHT 02", data['s2'], footer_text, font_url))
        slides_imgs.append(create_slide("CONCLUSIONE", data['s3'], footer_text, font_url))

        jpg_list = []
        for img in slides_imgs:
            buf = io.BytesIO(); img.save(buf, format='JPEG', quality=95); jpg_list.append(buf.getvalue())
        
        pdf_buf = io.BytesIO()
        slides_imgs[0].save(pdf_buf, format='PDF', save_all=True, append_images=slides_imgs[1:])
        
        send_email_kit(post_type, f"Ecco il kit per {post_type}.\n\n---COPY---\n{data['copy']}", jpg_list, pdf_buf.getvalue())
    else:
        print("Nessun post oggi.")

if __name__ == "__main__":
    main()
