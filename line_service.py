from linebot.models import FlexSendMessage

def create_flex_message(analysis_text):
    """
    Creates a Line Flex Message based on the structure returned by Gemini.
    Parsing relies on the separators used in the system prompt.
    """
    
    # Check for Error condition
    # Check for Error condition
    if analysis_text.startswith("Error"):
        # Custom Error Messages
        title = "ขอโทษเด้อ"
        header_color = "#1DB446"
        treatment = ""
        phaya = ""
        
        if "429" in analysis_text:
            body = "โอ๊ย! คนไข้หลายโพด หมอวินหัวแล้ว (Quota Exceeded) มื้ออื่นจั่งมาใหม่เด้อครับ"
        elif "404" in analysis_text:
            body = "หมอหาตำรารักษาบ่พ้อ สงสัยปลวกกินหมดแล้ว (Model Not Found / 404)"
        elif "500" in analysis_text:
            body = "โรงหมอไฟดับ เครื่องมือพัง (Server Error 500) รอจักคราวเด้อ"
        else:
            # Default generic error
            body = "หมอพืชกะจนปัญญา ระบบมันขัดข้องอีหลี (Unknown Error)"
            # Append original error for debugging if needed, or keep it clean
            # body += f"\n({analysis_text})"  
    else:
        # Default fallback content
        title = "หมอพืชอีสาน"
        body = analysis_text
        treatment = ""
        phaya = ""
        header_color = "#1DB446"

        # Simple parsing logic based on the "-----------------------" separator
        try:
            parts = analysis_text.split('-----------------------')
            # Only treat parts[0] as title if there is at least one separator
            if len(parts) > 1:
                title = parts[0].strip().replace('[', '').replace(']', '')
                body = parts[1].strip()
            else:
                # No separator found, use default title and full text as body
                title = "หมอพืชอีสาน"
                body = analysis_text.strip()
            
            if len(parts) >= 3:
                treatment = parts[2].strip()
            if len(parts) >= 4:
                phaya = parts[3].strip().replace('🎵 ผญาพาเพลิน:', '').replace('🎵 เกร็ดความรู้:', '').strip()
                
        except Exception as e:
            print(f"Parsing error: {e}")
            pass

    # Construct Flex Bubble
    # Split title into Thai and English if possible
    title_thai = title
    title_eng = ""
    
    if "(" in title:
        parts_title = title.split("(", 1)
        title_thai = parts_title[0].strip()
        title_eng = "(" + parts_title[1].strip()

    contents = [
        {
            "type": "text",
            "text": title_thai,
            "weight": "bold",
            "size": "xl",
            "color": header_color,
            "wrap": True
        }
    ]

    if title_eng:
        contents.append({
            "type": "text",
            "text": title_eng,
            "weight": "regular",
            "size": "md",
            "color": header_color,
            "wrap": True
        })

    contents.extend([
        {
            "type": "separator",
            "margin": "md"
        },
        {
            "type": "text",
            "text": body,
            "wrap": True,
            "margin": "md",
            "size": "sm"
        }
    ])
    
    if treatment:
        contents.append({
            "type": "separator",
            "margin": "md"
        })
        contents.append({
            "type": "text",
            "text": "วิธีรักษา/วิธีใช้:",
            "weight": "bold",
            "margin": "md",
            "size": "sm",
            "color": "#ff9800"
        })
        contents.append({
            "type": "text",
            "text": treatment,
            "wrap": True,
            "size": "sm"
        })

    if phaya:
        contents.append({
            "type": "separator",
            "margin": "md"
        })
        contents.append({
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#f0f0f0",
            "cornerRadius": "md",
            "paddingAll": "md",
            "margin": "md",
            "contents": [
                {
                    "type": "text",
                    "text": "🎵 ผญาพาเพลิน",
                    "weight": "bold",
                    "size": "xs",
                    "color": "#888888"
                },
                {
                    "type": "text",
                    "text": phaya,
                    "wrap": True,
                    "size": "sm",
                    "style": "italic",
                    "margin": "sm"
                }
            ]
        })

    flex_content = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": contents
        }
    }

    return FlexSendMessage(
        alt_text=f"แจ้งเตือน: {title}",
        contents=flex_content
    )
