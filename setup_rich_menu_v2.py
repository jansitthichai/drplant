import requests
import json
import os

# ==========================================
# 1. ใส่ Token ของคุณตรงนี้
# ==========================================
CHANNEL_ACCESS_TOKEN = 'm0xWnzVynmTOW+qp3nH+PLqakxhEG1gIQJAL+7M11jgm2ZMcvlGGeQjiLOpLODe9v174ETLV6bzmzLwv+xNCVu7igm0pIHJ05ly3XYbgSJdVuAwdLQfKSrmavfo+t0j6bhfc1lelXQtSPsBzrI/LlgdB04t89/1O/w1cDnyilFU='

# ชื่อไฟล์รูปภาพ (ต้องวางอยู่คู่กับไฟล์นี้)
IMAGE_FILENAME = 'rich_menu_image.png' 

# ==========================================
# 2. กำหนด Header สำหรับยิง API
# ==========================================
headers_json = {
    'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
    'Content-Type': 'application/json'
}

headers_image = {
    'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}',
    'Content-Type': 'image/png' # ถ้าเป็น jpg ให้แก้เป็น image/jpeg
}

def setup_rich_menu():
    print("🚀 กำลังเริ่มสร้าง Rich Menu (แบบยิงตรง)...")

    # ---------------------------------------------------
    # STEP 1: สร้างโครงสร้างเมนู (Create Rich Menu Object)
    # ---------------------------------------------------
    url_create = 'https://api.line.me/v2/bot/richmenu'
    
    # กำหนด Layout แบบ 3 ช่อง (ซ้าย-กลาง-ขวา)
    # Action type: "camera" คือคำสั่งเปิดกล้อง
    body = {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": "IsanPlant_Menu_Final",
        "chatBarText": "เมนูหมอพืช",
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
                "action": {"type": "uri", "label": "School", "uri": "http://www.strisuksa.ac.th/app/drplant/index.html"}
            },
            {
                "bounds": {"x": 833, "y": 0, "width": 833, "height": 843},
                "action": {"type": "camera", "label": "Scan"}  # <--- จุดสั่งเปิดกล้อง
            },
            {
                "bounds": {"x": 1666, "y": 0, "width": 834, "height": 843},
                "action": {"type": "uri", "label": "Manual", "uri": "http://www.strisuksa.ac.th/app/drplant/manual.html"}
            }
        ]
    }

    req = requests.post(url_create, headers=headers_json, data=json.dumps(body))
    
    if req.status_code != 200:
        print(f"❌ สร้างเมนูไม่สำเร็จ: {req.text}")
        return

    rich_menu_id = req.json()['richMenuId']
    print(f"✅ สร้าง ID สำเร็จ: {rich_menu_id}")

    # ---------------------------------------------------
    # STEP 2: อัปโหลดรูปภาพ (Upload Image)
    # ---------------------------------------------------
    print("⏳ กำลังอัปโหลดรูปภาพ (ขั้นตอนนี้อาจใช้เวลาแป๊บนึง)...")
    
    # URL สำหรับอัปโหลดรูป ต้องใช้ api-data.line.me
    url_upload = f'https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content'
    
    try:
        with open(IMAGE_FILENAME, 'rb') as f:
            image_data = f.read()
            req_upload = requests.post(url_upload, headers=headers_image, data=image_data)
            
            if req_upload.status_code != 200:
                print(f"❌ อัปโหลดรูปไม่ผ่าน: {req_upload.text}")
                return
            print("✅ อัปโหลดรูปภาพสำเร็จ")
            
    except FileNotFoundError:
        print(f"❌ หาไฟล์รูป '{IMAGE_FILENAME}' ไม่เจอ! กรุณาเช็คชื่อไฟล์")
        return

    # ---------------------------------------------------
    # STEP 3: ตั้งค่าเป็นเมนูเริ่มต้น (Set as Default)
    # ---------------------------------------------------
    url_default = f'https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}'
    req_default = requests.post(url_default, headers=headers_json)

    if req_default.status_code == 200:
        print("\n🎉 SETUP COMPLETE! เมนูขึ้นแล้วครับ (ถ้าไม่ขึ้นให้ Block/Unblock บอท 1 ครั้ง)")
    else:
        print(f"\n⚠️ ติดปัญหาตอนตั้งค่า Default: {req_default.text}")

if __name__ == "__main__":
    setup_rich_menu()