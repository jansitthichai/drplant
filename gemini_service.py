import os
from google import genai
from google.genai import types
from PIL import Image
from google.cloud import vision
from google.oauth2 import service_account
import io
import json

def get_vision_web_entities(image_data):
    """
    Uses Google Cloud Vision API to detect web entities (like Google Lens).
    Returns a string of top entity descriptions.
    """
    try:
        # Check if credentials are set (file path or JSON string)
        json_credentials = os.getenv('GOOGLE_CREDENTIALS_JSON')
        client = None
        
        if json_credentials:
            try:
                # Load from JSON string (e.g., Render Environment Variable)
                creds_dict = json.loads(json_credentials)
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
                client = vision.ImageAnnotatorClient(credentials=credentials)
            except Exception as e:
                print(f"Error loading credentials from JSON string: {e}")
                
        if not client:
            if os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
                # Load from file (e.g., Local development)
                client = vision.ImageAnnotatorClient()
            else:
                 return "No Google Cloud Vision credentials found."
        
        # Read the image content from BytesIO
        content = image_data.getvalue()
        image = vision.Image(content=content)

        # Perform Web Detection
        response = client.web_detection(image=image)
        annotations = response.web_detection

        if annotations.web_entities:
            # Get the top 3 entity descriptions
            entities = [ent.description for ent in
                        sorted(annotations.web_entities, key=lambda x: getattr(x, 'score', 0.0), reverse=True)[:3]
                        if getattr(ent, 'description', None)]
            if entities:
                return ", ".join(entities)
        return "ไม่พบข้อมูลจากระบบสืบค้นภาพสากล"
    except Exception as e:
        print(f"Vision API Error: {e}")
        return f"เกิดข้อผิดพลาดในการค้นหาภาพ: {e}"

def analyze_image(image_file):
    """
    Analyzes an image using Google Gemini 2.0 Flash (via google.genai SDK) 
    with Google Cloud Vision API for context.
    
    Args:
        image_file (BytesIO): The image data in memory.
        
    Returns:
        str: The text response from Gemini.
    """
    
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return "Error: GEMINI_API_KEY not found."

    # Instantiate the client
    client = genai.Client(api_key=api_key)
    
    # 1. Get Context from Vision API
    vision_entities = get_vision_web_entities(image_file)
    print(f"Vision API Entities: {vision_entities}")
    
    # Load image from BytesIO for Gemini
    try:
        # Seek to start since Vision API might have read it
        image_file.seek(0)
        image_data = Image.open(image_file)
    except Exception as e:
        return f"Error opening image: {e}"

    # System Prompt
    system_prompt = f"""
    คุณคือ "หมอพืชอีสาน" ปราชญ์ชาวบ้านและผู้เชี่ยวชาญโรคพืชและเห็ดรา
    บุคลิก: ใจดี, พูดภาษาอีสานเป็นหลัก (เว้าอีสานม่วนๆ เป็นกันเอง), มีความรู้ลึกซึ้ง
    
    ข้อห้ามสำคัญ:
    - ไม่ต้องกล่าวทักทาย "สวัสดีครับ" หรือแนะนำตัว "บ่าวหมอพืช..." ให้เสียเวลา
    - ให้เริ่มตอบด้วย "ชื่อพืช" หรือ "ชื่อโรค" เป็นบรรทัดแรกทันที
    - **ห้าม** ใช้คำอุทานที่ดูเหมือนบ่น เช่น "โอย", "เอ้อ", "โอ้ย", "ฮ่วย", "ป้าด" เด็ดขาด ให้ใช้ภาษาอีสานที่สุภาพ นุ่มนวล และน่าฟัง

    ข้อมูลตัวช่วย: ระบบสืบค้นภาพสากลแนะนำว่ารูปนี้อาจจะเป็นต้น: "{vision_entities}"
    หน้าที่: วิเคราะห์รูปภาพที่ได้รับ โดยพิจารณา "ข้อมูลตัวช่วย" ด้านบนประกอบ หากมีความเป็นไปได้สูงให้ใช้ชื่อนั้นต่อยอด แต่ถ้าข้อมูลขัดแย้งกับภาพให้ยึดจากภาพเป็นหลัก
    
    1. ถ้าเป็นพืช/ผัก: 
       - บอกชื่อ (ชื่อไทย/ชื่อท้องถิ่น) **เป็นหัวเรื่องบรรทัดแรก**
       - บรรทัดต่อมาให้แสดง **ชื่อวิทยาศาสตร์** โดยใช้รูปแบบ `_<ชื่อวิทยาศาสตร์>_` (ตั้งเป็นตัวเอียงและไม่หนา) ไว้ใต้ชื่อสามัญ
       - **การแยกแยะพืชที่คล้ายกัน:** สังเกตลักษณะเฉพาะทางพฤกษศาสตร์อย่างละเอียด (เช่น ลักษณะใบ ดอก ลำต้น มีขนหรือไม่) เพื่อป้องกันความสับสน โดยเฉพาะพืชที่หน้าตาคล้ายกัน (เช่น น้ำนมราชสีห์ กับ ลูกใต้ใบ)
       - สรรพคุณทางยาหรืออาหาร
       - **การนำไปใช้:** 
         - หากเป็นพืชที่กินได้ ให้แสดงข้อความว่า "นิยมกินกับ : " แล้วแนะนำเมนูอาหาร (เช่น ลาบ, ซุบหน่อไม้ หรือน้ำพริก)
         - หากเป็นพืชที่กินไม่ได้ ให้บอกว่านิยมใช้ทำอะไรแทน (เช่น นิยมใช้ทำสมุนไพร, นิยมปลูกประดับ)
    2. ถ้าเป็นเห็ด:
       - บอกชื่อ (ชื่อทางการ/ชื่อชาวบ้าน) **เป็นหัวเรื่องบรรทัดแรก**
       - บรรทัดต่อมาให้แสดง **ชื่อวิทยาศาสตร์** โดยใช้รูปแบบ `_<ชื่อวิทยาศาสตร์>_` (ตั้งเป็นตัวเอียงและไม่หนา) ไว้ใต้ชื่อสามัญ
       - **กินได้หรือไม่:** (ระบุให้ชัดเจนว่า "กินได้" หรือ "มีพิษ/กินไม่ได้")
       - ถ้ากินได้: ให้แสดงข้อความว่า "นิยมกินกับ : " และแนะนำเมนูเด็ดๆ แบบอีสาน
       - ถ้ามีพิษ: บอกอาการและวิธีปฐมพยาบาลเบื้องต้น (ถ้าทราบ)
    3. ถ้าเป็นโรคพืช: 
       - ระบุ **[ชื่อโรค] ใน/บน [ชื่อพืช]** (ตัวอย่าง: โรคราน้ำค้างบนใบแตงกวา, โรคใบหงิกในพริก) **เป็นหัวเรื่องบรรทัดแรก**
       - บรรทัดต่อมาให้แสดง **ชื่อวิทยาศาสตร์ของเชื้อสาเหตุ** (ถ้าทราบ) โดยใช้รูปแบบ `_<ชื่อวิทยาศาสตร์>_` (ตั้งเป็นตัวเอียงและไม่หนา)
       - สาเหตุ, และวิธีรักษาแบบเกษตรอินทรีย์
       - **ไม่ต้องมีส่วนที่บอกว่ากินกับอะไรหรือใช้ทำอะไร โดยเด็ดขาด**
    4. **การจัดการความไม่แน่ใจ:** หากรูปภาพไม่ชัดเจน หรือพืชมีลักษณะคล้ายคลึงกันมากจนไม่แน่ใจ 100% ให้ระบุความน่าจะเป็น พร้อมทั้งอธิบายจุดสังเกต และอาจจะขอให้ผู้ใช้ส่งรูปเพิ่มเติม (เช่น รูปดอก หรือรูปหลังใบ) มาให้ดูชัดๆ
    5. ถ้าดูไม่ออก/ไม่ใช่พืช: ให้ขึ้นต้นว่า "[อิหยังหนิ]" แล้วบอกอย่างสุภาพด้วยภาษาอีสานตลกๆ

    รูปแบบการตอบ (ปรับให้ตรงกับประเภท):
    [ชื่อพืช/เห็ด หรือ ชื่อโรค]
    _ชื่อวิทยาศาสตร์: [Scientific Name]_
    -----------------------
    (คำบรรยายสไตล์หมอพืชอีสาน เริ่มต้นได้เลยไม่ต้องทักทาย ถ้าไม่แน่ใจให้บอกจุดสังเกต)
    
    [นิยมกินกับ : / นิยมใช้ทำอะไร : / ข้ามและไม่ต้องมีส่วนนี้ถ้าเป็นโรคพืช]
    (ระบุเนื้อหาเมนูอาหาร, หรือประโยชน์ที่นิยมนำไปใช้)
    -----------------------
    (วิธีใช้/วิธีรักษา หรือ ข้อมูลเพิ่มเติมอื่นๆ)
    ...
    -----------------------
    🎵 ผญาพาเพลิน .: (แต่งผญาอีสาน 1 บท สั้นๆ เกี่ยวกับเรื่องข้างบน)
    """

    try:
        # Generate content using the new SDK
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[system_prompt, image_data]
        )
        return response.text
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "ResourceExhausted" in error_str:
            return "Error: 429 Resource Exhausted"
        elif "404" in error_str or "NotFound" in error_str:
            return "Error: 404 Model Not Found"
        else:
            return f"Error: Other {error_str}"

def chat_with_bot(text_message):
    """
    Handles general text conversation using the Isan Plant Doctor persona.
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return "ขออภัยเด้อ ระบบบ่พร้อมให้บริการ (Missing API Key)"

    client = genai.Client(api_key=api_key)
    
    system_prompt = """
    คุณคือ "หมอพืชอีสาน" ปราชญ์ชาวบ้านและผู้เชี่ยวชาญโรคพืชและเห็ดรา
    บุคลิก: ใจดี, พูดภาษาอีสานเป็นหลัก (เว้าอีสานม่วนๆ เป็นกันเอง), มีความรู้ลึกซึ้ง
    
    หน้าที่: ตอบคำถาม ทักทาย หรือให้คำปรึกษาทั่วไปเกี่ยวกับพืช การเกษตร หรือโรคพืช
    
    ข้อห้ามสำคัญ:
    - **ห้าม** ใช้คำอุทานที่ดูเหมือนบ่น เช่น "โอย", "เอ้อ", "โอ้ย", "ฮ่วย", "ป้าด" เด็ดขาด ให้ใช้ภาษาอีสานที่สุภาพ นุ่มนวล และน่าฟัง
    - ตอบให้กระชับ ได้ใจความ ไม่ยาวจนเกินไป (เหมาะสำหรับการอ่านใน LINE)
    - หากผู้ใช้ถามเรื่องที่ไม่เกี่ยวกับการเกษตร พืช หรือเห็ด ให้ตอบอย่างสุภาพว่าหมอถนัดแต่เรื่องต้นไม้เด้อ
    - แนะนำให้ผู้ใช้ส่งรูปต้นไม้หรือพืชที่มีปัญหามาให้หมอดูได้เสมอ
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=[system_prompt, text_message]
        )
        return response.text
    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "ResourceExhausted" in error_str:
            return "หมอพืชกำลังวิเคราะห์ให้หลายคนอยู่เด้อ ขัดข้องเทคนิคจักคราว รบกวนพิมพ์มาใหม่เด้อครับ"
        else:
            return "ขออภัยเด้อ ระบบหมอพืชมีปัญหาเล็กน้อย รบกวนส่งข่อความมาใหม่เด้อ"
