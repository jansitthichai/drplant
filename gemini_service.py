import os
import traceback
from google import genai
from google.genai import types
from PIL import Image
from google.cloud import vision
from google.oauth2 import service_account
import io
import json

# gemini-2.0-flash ถูกเลิกแล้ว — ค่าเริ่มต้นใช้ 2.5-flash (override ได้ด้วย GEMINI_MODEL)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


def get_gemini_model():
    return os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL


def extract_gemini_text(response):
    """อ่านข้อความจาก response อย่างปลอดภัย (กันกรณีถูก block / ไม่มี text)."""
    try:
        text = response.text
        if text and text.strip():
            return text
    except Exception as e:
        print(f"Gemini response.text error: {e}")

    try:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return None
        parts = getattr(candidates[0].content, "parts", None) or []
        chunks = [p.text for p in parts if getattr(p, "text", None)]
        if chunks:
            return "".join(chunks)
    except Exception as e:
        print(f"Gemini candidates parse error: {e}")
    return None


def format_gemini_user_error(error, for_chat=True):
    """
    แปลง error ของ Gemini เป็นข้อความภาษาไทยที่บอกสาเหตุชัด
    และพิมพ์รายละเอียดเต็มลง log สำหรับ Render.
    """
    error_str = str(error)
    print(f"Gemini API Error: {error_str}")
    traceback.print_exc()

    lower = error_str.lower()

    if "429" in error_str or "resourceexhausted" in lower or "quota" in lower:
        msg = (
            "หมอพืชกำลังวิเคราะห์ให้หลายคนอยู่เด้อ (โควต้า API เต็มชั่วคราว) "
            "รบกวนพิมพ์มาใหม่จักคราวเด้อครับ"
        )
    elif "404" in error_str or "not_found" in lower or "no longer available" in lower:
        msg = (
            "ขออภัยเด้อ โมเดล AI ที่ระบบใช้อยู่ถูกยกเลิกหรือหาไม่เจอ "
            f"(model={get_gemini_model()}) รบกวนแจ้งผู้ดูแลอัปเดตชื่อโมเดลเด้อ"
        )
    elif "401" in error_str or "403" in error_str or "permission" in lower or "api key" in lower or "invalid" in lower and "key" in lower:
        msg = (
            "ขออภัยเด้อ กุญแจ Gemini API ใช้บ่ได้หรือหมดสิทธิ์ "
            "รบกวนตรวจ GEMINI_API_KEY ในเซิร์ฟเวอร์เด้อ"
        )
    elif "safety" in lower or "blocked" in lower or "prohibit" in lower:
        msg = "ขออภัยเด้อ ระบบกันเนื้อหาไว้ชั่วคราว รบกวนส่งข้อความหรือรูปใหม่เด้อ"
    elif "timeout" in lower or "timed out" in lower or "deadline" in lower:
        msg = "ขออภัยเด้อ การเชื่อมต่อ AI ช้าเกินกำหนด รบกวนลองใหม่อีกทีเด้อ"
    else:
        # สรุปสั้นๆ ให้ผู้ใช้เห็นสาเหตุ โดยไม่ยาวเกินใน LINE
        short = error_str.replace("\n", " ").strip()
        if len(short) > 160:
            short = short[:160] + "…"
        msg = f"ขออภัยเด้อ ระบบหมอพืชมีปัญหาเล็กน้อย ({short}) รบกวนส่งใหม่อีกทีเด้อ"

    if not for_chat:
        # analyze_image ใช้ prefix Error เพื่อให้ app.py สลับไป OpenAI ได้
        if "429" in error_str or "resourceexhausted" in lower:
            return "Error: 429 Resource Exhausted"
        if "404" in error_str or "not_found" in lower or "no longer available" in lower:
            return "Error: 404 Model Not Found"
        return f"Error: Other {error_str}"

    return msg


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
                 # Vision API is optional
                 return None
        
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
    Analyzes an image using Google Gemini (via google.genai SDK)
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
    model_name = get_gemini_model()
    
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

    # Persona and System Instructions
    persona = """
    คุณคือ "หมอพืชอีสาน" ปราชญ์ชาวบ้านและผู้เชี่ยวชาญโรคพืชและเห็ดรา
    บุคลิก: ใจดี, พูดภาษาอีสานเป็นหลัก (เว้าอีสานม่วนๆ เป็นกันเอง), มีความรู้ลึกซึ้ง
    """

    vision_context = ""
    if vision_entities:
        vision_context = f'\n    ข้อมูลตัวช่วย: ระบบสืบค้นภาพสากลแนะนำว่ารูปนี้อาจจะเป็นต้น: "{vision_entities}"\n'

    system_prompt = f"""
    {persona}
    
    ข้อห้ามสำคัญ:
    - ไม่ต้องกล่าวทักทาย "สวัสดีครับ" หรือแนะนำตัว "บ่าวหมอพืช..." ให้เสียเวลา
    - ให้เริ่มตอบด้วย "ชื่อพืช" หรือ "ชื่อโรค" เป็นบรรทัดแรกทันที
    - **ห้าม** ใช้คำอุทานที่ดูเหมือนบ่น เช่น "โอย", "เอ้อ", "โอ้ย", "ฮ่วย", "ป้าด" เด็ดขาด ให้ใช้ภาษาอีสานที่สุภาพ นุ่มนวล และน่าฟัง
    {vision_context}
    
    กระบวนการวิเคราะห์เชิงลึก (Chain-of-Thought):
    ก่อนจะระบุชื่อ ให้คุณพิจารณาลักษณะทางพฤกษศาสตร์อย่างละเอียดตามลำดับ:
    1. ลักษณะใบ: ขอบใบจักไหม? มีขนไหม? ใบมันหรือใบด้าน?
    2. สีลำต้น: เขียว แดง หรือม่วง?
    3. การจัดเรียง: ใบออกแบบคู่หรือสลับ?
    
    คู่มือแยกแยะพิเศษ (Differentiating Guide):
    - **กะเพรา (Gaprao):** ลำต้นและใบมีขนเห็นชัด ขอบใบหยักฟันเลื่อย กลิ่นฉุนร้อน (ลำต้นอาจแดงหรือเขียว)
    - **แมงลัก (อีตู่ - Maenglak):** ใบสีเขียวอ่อน ขนน้อยกว่ากะเพรา กลิ่นหอมนวล (นิยมใส่แกงหน่อไม้)
    - **โหระพา (Horapha):** ลำต้นสีม่วงเข้ม ใบสีเขียวเข้ม ผิวมัน ลำต้นไม่มีขน กลิ่นหอมเฉพาะตัว
    - **ลูกใต้ใบ vs น้ำนมราชสีห์:** ดูตำแหน่งลูก (ลูกใต้ใบจะเรียงใต้ก้านใบ, น้ำนมราชสีห์เป็นกลุ่มที่ข้อ)

    หน้าที่: วิเคราะห์รูปภาพที่ได้รับ โดยพิจารณา "ข้อมูลตัวช่วย" และ "คู่มือแยกแยะ" ประกอบ
    
    1. ถ้าเป็นพืช/ผัก: 
       - บอกชื่อ (ชื่อไทย/ชื่อท้องถิ่น) **เป็นหัวเรื่องบรรทัดแรก**
       - บรรทัดต่อมาให้แสดง **ชื่อวิทยาศาสตร์** โดยใช้รูปแบบ `_<ชื่อวิทยาศาสตร์>_` (ตั้งเป็นตัวเอียงและไม่หนา) ไว้ใต้ชื่อสามัญ
       - **การแยกแยะพืชที่คล้ายกัน:** สังเกตลักษณะเฉพาะทางพฤกษศาสตร์อย่างละเอียด (เช่น ลักษณะใบ ดอก ลำต้น มีขนหรือไม่) เพื่อป้องกันความสับสน โดยเฉพาะพืชที่หน้าตาคล้ายกัน (เช่น น้ำนมราชสีห์ กับ ลูกใต้ใบ)
       - สรรพคุณทางยาหรืออาหาร
       - **การนำไปใช้:** 
         - หากเป็นพืชที่กินได้ ให้แสดงข้อความว่า "นิยมกินกับ : " แล้วแนะนำเมนูอาหาร
         - หากเป็นพืชที่กินไม่ได้ ให้บอกว่านิยมใช้ทำอะไรแทน
    2. ถ้าเป็นเห็ด:
       - บอกชื่อ (ชื่อทางการ/ชื่อชาวบ้าน) **เป็นหัวเรื่องบรรทัดแรก**
       - บรรทัดต่อมาให้แสดง **ชื่อวิทยาศาสตร์** โดยใช้รูปแบบ `_<ชื่อวิทยาศาสตร์>_`
       - กินได้หรือไม่ และเมนูแนะนำ (หากกินได้) หรือวิธีปฐมพยาบาล (หากมีพิษ)
    3. ถ้าเป็นโรคพืช: 
       - ระบุ **[ชื่อโรค] ใน/บน [ชื่อพืช]** (ตัวอย่าง: โรคราน้ำค้างบนใบแตงกวา, โรคใบหงิกในพริก) **เป็นหัวเรื่องบรรทัดแรก**
       - บรรทัดต่อมาให้แสดง **ชื่อวิทยาศาสตร์ของเชื้อสาเหตุ** (ถ้าทราบ) โดยใช้รูปแบบ `_<ชื่อวิทยาศาสตร์>_` (ตั้งเป็นตัวเอียงและไม่หนา)
       - สาเหตุ, และวิธีรักษาแบบเกษตรอินทรีย์
       - **ไม่ต้องมีส่วนที่บอกว่ากินกับอะไรหรือใช้ทำอะไร โดยเด็ดขาด**
    4. **การจัดการความไม่แน่ใจ:** หากรูปภาพไม่ชัดเจน หรือพืชมีลักษณะคล้ายคลึงกันมากจนไม่แน่ใจ 100% ให้ระบุความน่าจะเป็น พร้อมทั้งอธิบายจุดสังเกต และอาจจะขอให้ผู้ใช้ส่งรูปเพิ่มเติม (เช่น รูปดอก หรือรูปหลังใบ) มาให้ดูชัดๆ
    5. ถ้าดูไม่ออก/ไม่ใช่พืช: ให้ขึ้นต้นว่า "[อิหยังหนิ]" แล้วบอกอย่างสุภาพด้วยภาษาอีสานตลกๆ

    รูปแบบการตอบ:
    [ชื่อพืช/เห็ด หรือ ชื่อโรค]
    _ชื่อวิทยาศาสตร์: [Scientific Name]_
    -----------------------
    (คำบรรยายสไตล์หมอพืชอีสาน เริ่มต้นด้วยการอธิบายลักษณะเด่นที่สังเกตเห็นก่อน แล้วจึงสรุปว่าเป็นอะไร)
    
    [นิยมกินกับ : / นิยมใช้ทำอะไร : / ข้ามถ้าเป็นโรคพืช]
    ...
    -----------------------
    (วิธีใช้/วิธีรักษา หรือ ข้อมูลเพิ่มเติม)
    ...
    -----------------------
    🎵 ผญาพาเพลิน .: (แต่งผญาอีสาน 1 บท)
    """

    try:
        print(f"analyze_image using model={model_name}")
        response = client.models.generate_content(
            model=model_name,
            contents=[system_prompt, image_data],
            config=types.GenerateContentConfig(
                temperature=0.0,
            )
        )
        text = extract_gemini_text(response)
        if not text:
            return "Error: Other empty or blocked Gemini response"
        return text
    except Exception as e:
        return format_gemini_user_error(e, for_chat=False)

def chat_with_bot(text_message, history=None, last_prediction=None):
    """
    Handles general text conversation using the Isan Plant Doctor persona.
    Uses recent chat history and the latest image analysis when available.
    """
    api_key = os.getenv('GEMINI_API_KEY')
    if not api_key:
        return "ขออภัยเด้อ ระบบบ่พร้อมให้บริการ (ยังไม่มี GEMINI_API_KEY บนเซิร์ฟเวอร์)"

    client = genai.Client(api_key=api_key)
    model_name = get_gemini_model()

    context_parts = []
    if last_prediction:
        # Keep context compact for the model
        prediction_snippet = last_prediction.strip()
        if len(prediction_snippet) > 1500:
            prediction_snippet = prediction_snippet[:1500] + "…"
        context_parts.append(
            "ผลการวิเคราะห์รูปล่าสุดของผู้ใช้นี้ (ใช้อ้างอิงเมื่อผู้ใช้ถามต่อ):\n"
            f"{prediction_snippet}"
        )

    if history:
        lines = []
        for role, content in history:
            label = "ผู้ใช้" if role == "user" else "หมอพืช"
            lines.append(f"{label}: {content}")
        context_parts.append("ประวัติการสนทนาล่าสุด:\n" + "\n".join(lines))

    context_block = ""
    if context_parts:
        context_block = "\n\n".join(context_parts) + "\n\n"

    system_prompt = f"""
    คุณคือ "หมอพืชอีสาน" ปราชญ์ชาวบ้านและผู้เชี่ยวชาญโรคพืชและเห็ดรา
    บุคลิก: ใจดี, พูดภาษาอีสานเป็นหลัก (เว้าอีสานม่วนๆ เป็นกันเอง), มีความรู้ลึกซึ้ง
    
    หน้าที่: ตอบคำถาม ทักทาย หรือให้คำปรึกษาทั่วไปเกี่ยวกับพืช การเกษตร หรือโรคพืช
    - หากมี "ผลการวิเคราะห์รูปล่าสุด" และผู้ใช้ถามต่อเนื่อง ให้ตอบอิงผลนั้นก่อน
    - หากมีประวัติสนทนา ให้ตอบต่อเนื่องตามบริบท ไม่ถามซ้ำสิ่งที่รู้แล้ว
    - ถ้าผู้ใช้บอกลักษณะพืช/อาการด้วยข้อความ ให้ช่วยวิเคราะห์และถามจุดที่ยังไม่ชัดได้
    
    ข้อห้ามสำคัญ:
    - **ห้าม** ใช้คำอุทานที่ดูเหมือนบ่น เช่น "โอย", "เอ้อ", "โอ้ย", "ฮ่วย", "ป้าด" เด็ดขาด ให้ใช้ภาษาอีสานที่สุภาพ นุ่มนวล และน่าฟัง
    - ตอบให้กระชับ ได้ใจความ ไม่ยาวจนเกินไป (เหมาะสำหรับการอ่านใน LINE)
    - หากผู้ใช้ถามเรื่องที่ไม่เกี่ยวกับการเกษตร พืช หรือเห็ด ให้ตอบอย่างสุภาพว่าหมอถนัดแต่เรื่องต้นไม้เด้อ
    - แนะนำให้ส่งรูปเมื่อจำเป็นต่อการวินิจฉัย ไม่ต้องชวนส่งรูปทุกข้อความ
    
    {context_block}ข้อความล่าสุดของผู้ใช้:
    {text_message}
    """
    
    try:
        print(f"chat_with_bot using model={model_name}")
        response = client.models.generate_content(
            model=model_name,
            contents=[system_prompt]
        )
        text = extract_gemini_text(response)
        if not text:
            return (
                "ขออภัยเด้อ AI ตอบว่างหรือถูกบล็อกเนื้อหา "
                "รบกวนพิมพ์ข้อความใหม่หรือส่งรูปมาใหม่เด้อ"
            )
        return text
    except Exception as e:
        return format_gemini_user_error(e, for_chat=True)
