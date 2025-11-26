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

# --- FONT URLS (AFFIDABILI) ---
# Usiamo font molto pesanti (Bold/Black) per leggibilità
FONTS = {
    'cinema': 'https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Black.ttf',
    'intelligence': 'https://github.com/google/fonts/raw/main/ofl/playfairdisplay/PlayfairDisplay-Black.ttf',
    'music': 'https://github.com/google/fonts/raw/main/ofl/bebasneue/BebasNeue-Regular.ttf',
    'agency': 'https://github.com/google/fonts/raw/main/apache/robotoslab/RobotoSlab-Black.ttf'
}

def download_font(url):
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        return io.BytesIO(r.content)
    except: return None

def wrap_text(text, font, max_width, draw):
    """Calcola a capo automatico"""
    if not text: return []
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
    W, H = 1080, 1080 # Formato HD
    img = Image.new('RGB', (W, H), color='#0a0a0a') # Nero profondo
    draw = ImageDraw.Draw(img)
    
    font_bytes = download_font(font_url)
    
    # --- DIMENSIONI MAGGIORATE ---
    size_title = 130 if is_cover else 90 # Molto grande
    size_body = 70  # Molto leggibile
    size_footer = 35
    
    try:
        if font_bytes:
            font_title = ImageFont.truetype(font_bytes, size_title)
            font_bytes.seek(0)
            font_body = ImageFont.truetype(font_bytes, size_body)
            font_bytes.seek(0)
            font_footer = ImageFont.truetype(font_bytes, size_footer)
        else:
            raise Exception("Font fail")
    except:
        font_title = font_body = font_footer = ImageFont.load_default()

    # Colori Marte
    COL_ORANGE = '#ff5500'
    COL_WHITE = '#ffffff'
    COL_GREY = '#888888'

    # Margini
    margin_x = 100
    
    # TITOLO
    draw.text((margin_x, 100), str(title).upper(), font=font_title, fill=COL_ORANGE)
    
    # LINEA
    line_y = 100 + size_title + 30
    draw.line((margin_x, line_y, W-margin_x, line_y), fill=COL_ORANGE, width=6)

    # CORPO
    if not text or len(str(text)) < 2: text = "..."
    
    start_y = line_y + 80
    max_w = W - (margin_x * 2)
    
    lines = wrap_text(str(text), font_body, max_w, draw)
    current_y = start_y
    
    for line in lines:
        parts = line.split('*')
        current_x = margin_x
        for i, part in enumerate(parts):
            color = COL_ORANGE if i % 2 != 0 else COL_WHITE
            if not part: continue
            draw.text((current_x, current_y), part, font=font_body, fill=color)
            bbox = draw.textbbox((0, 0), part, font=font_body)
            current_x += (bbox[2] - bbox[0])
        current_y += size_body + 20 # Interlinea ampia

    # FOOTER
    draw.text((margin_x, H-120), str(footer), font=font_footer, fill=COL_GREY)
    
    return img

def get_gemini_content(prompt, context):
    full_prompt = f"""
    Sei un Senior Editor. 
    CONTESTO REALE DAL SITO: "{context}"
    
    Compito:
    1. Scrivi Copy LinkedIn (Terza persona, NO EMOJI).
    2. Crea 4 Slide sintetiche. 
    
    IMPORTANTE: 
    - Se il contesto è vuoto, scrivi "ERRORE LETTURA SITO".
    - Metti le *PAROLE CHIAVE* delle slide tra asterischi.
    
    OUTPUT FORMAT:
    [[COPY_START]] ... [[COPY_END]]
    [[TITOLO_START]] (Titolo Cover max 4 parole) [[TITOLO_END]]
    [[SLIDE1_START]] (Concetto 1 max 12 parole) [[SLIDE1_END]]
    [[SLIDE2_START]] (Concetto 2 max 12 parole) [[SLIDE2_END]]
    [[SLIDE3_START]] (Conclusione max 12 parole) [[SLIDE3_END]]
    
    Istruzione: {prompt}
    """
    try:
        response = model.generate_content(full_prompt)
        return response.text
    except Exception as e:
        return f"Errore AI: {e}"

def extract_tag(text, tag_name):
    pattern = f"\\[\\[{tag_name}_START\\]\\](.*?)\\[\\[{tag_name}_END\\]\\]"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""

def parse_response(text):
    data = {}
    data['copy'] = extract_tag(text, "COPY")
    data['titolo'] = extract_tag(text, "TITOLO")
    data['s1'] = extract_tag(text, "SLIDE1")
    data['s2'] = extract_tag(text, "SLIDE2")
    data['s3'] = extract_tag(text, "SLIDE3")
    
    if not data['copy']: data['copy'] = "Errore generazione copy."
    if not data['titolo']: data['titolo'] = "MARTE UPDATE"
    if not data['s1']: data['s1'] = "Dati non disponibili."
    return data

def scrape_section(url, selector):
    """Scarica testo usando ID precisi"""
    print(f"Scraping: {url} -> {selector}")
    try:
        r = requests.get(url, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        
        # Cerca selettore specifico
        el = soup.select_one(selector)
        if el:
            clean = el.get_text(" ", strip=True)
            return clean[:2500] # Max caratteri
            
        # Fallback per MSH: se non trova l'articolo, prende tutto il body
        if "msh" in url:
            return soup.body.get_text(" ", strip=True)[:2500]
            
    except Exception as e:
        return f"Errore tecnico scraping: {e}"
    return ""

def send_email_kit(subject, body, images_list, pdf_bytes):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = TARGET_EMAIL
    msg['Subject'] = f"📦 MEDIA KIT PRO: {subject}"
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

    # --- CALENDARIO PRECISO ---
    if weekday == 0: 
        post_type = "Cinema Cult"; font_key = 'cinema'
        link_url = "https://velvet.martestudios.com/cinema.html"
        # Prende esattamente il box vintage
        scraped_text = scrape_section(link_url, "#vintage-feed")
        prompt = "Slide educative sul film cult della settimana."

    elif weekday == 2: 
        post_type = "Intelligence"; font_key = 'intelligence'
        link_url = "https://msh.martestudios.com"
        # Prende il contenitore delle news
        scraped_text = scrape_section(link_url, "#news-feed") 
        if len(scraped_text) < 50: scraped_text = scrape_section(link_url, "article")
        prompt = "Slide analitiche sulla news di geopolitica odierna."

    elif weekday == 4: 
        post_type = "Music Vibe"; font_key = 'music'
        link_url = "https://velvet.martestudios.com/musica.html"
        scraped_text = scrape_section(link_url, "#vintage-feed")
        prompt = "Slide sull'album vintage della settimana."

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
        
        # Se lo scraping è vuoto, avvisiamo nella mail
        debug_msg = ""
        if not scraped_text or len(scraped_text) < 10:
            scraped_text = "NESSUN DATO TROVATO SUL SITO."
            debug_msg = "\n⚠️ ATTENZIONE: Il bot non ha trovato testo sul sito. Verifica che il sito sia aggiornato."

        raw = get_gemini_content(prompt, scraped_text)
        data = parse_response(raw)
        
        slides_imgs = []
        font_url = FONTS[font_key]
        footer_text = "MARTE STUDIOS"

        # Generazione Immagini
        slides_imgs.append(create_slide(data['titolo'], "Scorri ->", footer_text, font_url, is_cover=True))
        slides_imgs.append(create_slide("01", data['s1'], footer_text, font_url))
        slides_imgs.append(create_slide("02", data['s2'], footer_text, font_url))
        slides_imgs.append(create_slide("03", data['s3'], footer_text, font_url))

        jpg_list = []
        for img in slides_imgs:
            buf = io.BytesIO(); img.save(buf, format='JPEG', quality=95); jpg_list.append(buf.getvalue())
        
        pdf_buf = io.BytesIO()
        slides_imgs[0].save(pdf_buf, format='PDF', save_all=True, append_images=slides_imgs[1:])
        
        email_body = f"""
        KIT PRO ({post_type})
        
        {debug_msg}
        
        --- DATI LETTI DAL SITO (DEBUG) ---
        {scraped_text[:300]}...
        -----------------------------------
        
        --- COPY LINKEDIN ---
        {data['copy']}
        
        Link: {link_url}
        """
        
        send_email_kit(post_type, email_body, jpg_list, pdf_buf.getvalue())
    else:
        print("Nessun post oggi.")

if __name__ == "__main__":
    main()
