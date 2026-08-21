import os
import sys
import threading
import requests
import json
from io import BytesIO

from flask import Flask, request, abort, render_template
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageMessage

# Custom services
from gemini_service import analyze_image as analyze_image_gemini, chat_with_bot
from openai_service import analyze_image_openai
from line_service import create_flex_message
import database

load_dotenv()

print("--- Plant Doctor System Startup ---")

try:
    print("Initializing database...")
    database.init_db()
    print("Database initialized successfully.")
except Exception as e:
    print(f"CRITICAL ERROR: Failed to initialize database: {e}")
    # Don't exit here if you want to see other errors, but usually DB is required
    # sys.exit(1)

app = Flask(__name__, template_folder='.')

# LINE API Setup
APP_PORT = os.getenv('PORT', default=5000)
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

line_bot_api = None
handler = None

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    print('--- WARNING: Missing LINE API configuration ---')
    print('Please set LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET in environment variables.')
    print('The application will start, but LINE Webhook features will be unavailable.')
else:
    print("LINE API Credentials found. Initializing...")
    line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
    handler = WebhookHandler(CHANNEL_SECRET)

@app.route("/", methods=['GET', 'POST'])
def root():
    if request.method == 'POST':
        app.logger.warning("Webhook received at '/'! You forgot to add '/callback' to your Webhook URL in line developers console.")
        return "Error: Please set Webhook URL to end with /callback", 400
    return render_template('index.html')

@app.route("/manual.html")
def manual():
    return render_template('manual.html')

@app.route("/health")
def health():
    return "OK", 200


@app.route("/callback", methods=['POST'])
def callback():
    if not handler:
        app.logger.error("LINE Webhook Handler not initialized. Check environment variables.")
        return "Webhook Handler not initialized", 500

    # get X-Line-Signature header value
    signature = request.headers.get('X-Line-Signature')

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # Vercel serverless cannot reliably finish background threads after response.
    if os.getenv('VERCEL'):
        handle_webhook_events(body, signature)
    else:
        thread = threading.Thread(target=handle_webhook_events, args=(body, signature))
        thread.start()

    return 'OK'

def handle_webhook_events(body, signature):
    """
    Process webhook events in a separate thread.
    """
    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
    except Exception as e:
        print(f"Error handling webhook: {e}")

def show_loading_animation(user_id):
    """
    Shows a loading animation to the user using LINE Messaging API.
    """
    if not CHANNEL_ACCESS_TOKEN:
        return
    try:
        url = 'https://api.line.me/v2/bot/chat/loading/start'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {CHANNEL_ACCESS_TOKEN}'
        }
        data = {
            'chatId': user_id,
            'loadingSeconds': 20 # Maximum 60 seconds
        }
        response = requests.post(url, headers=headers, data=json.dumps(data))
        if response.status_code == 202:
            print(f"Successfully started loading animation for user: {user_id}")
        else:
            print(f"Failed to start loading animation: {response.text}")
    except Exception as e:
        print(f"Error showing loading animation: {e}")

if handler:
    @handler.add(MessageEvent, message=ImageMessage)
    def handle_image_message(event):
        if not line_bot_api:
            return
        user_id = event.source.user_id
        message_id = event.message.id
        message_content = line_bot_api.get_message_content(message_id)
        
        # Read image content into memory
        image_data = BytesIO(message_content.content)
        
        # Send to Gemini
        analysis_result = ""
        try:
            # Show loading animation
            show_loading_animation(user_id)
            
            # Try Gemini First
            analysis_result = analyze_image_gemini(image_data)

            # Check for explicit error strings from Gemini service
            if "Error" in analysis_result and ("429" in analysis_result or "404" in analysis_result or "Resource Exhausted" in analysis_result):
                print(f"Gemini Error ({analysis_result}). Switching to OpenAI...")
                analysis_result = analyze_image_openai(image_data)
            
            # Log basic info to DB (Initial prediction)
            database.log_feedback(user_id, message_id, analysis_result, status='pending')
            database.save_chat(user_id, "user", "[ผู้ใช้ส่งรูปมาให้วิเคราะห์]")
            analysis_for_chat = analysis_result if len(analysis_result) <= 800 else analysis_result[:800] + "…"
            database.save_chat(user_id, "assistant", analysis_for_chat)

            # Create Flex Message
            flex_message = create_flex_message(analysis_result)
            
            line_bot_api.reply_message(
                event.reply_token,
                flex_message
            )
        except Exception as e:
            print(f"Error processing image: {e}")
            try:
                analysis_result = analyze_image_openai(image_data)
                database.log_feedback(user_id, message_id, analysis_result, status='pending')
                database.save_chat(user_id, "user", "[ผู้ใช้ส่งรูปมาให้วิเคราะห์]")
                analysis_for_chat = analysis_result if len(analysis_result) <= 800 else analysis_result[:800] + "…"
                database.save_chat(user_id, "assistant", analysis_for_chat)
                flex_message = create_flex_message(analysis_result)
                line_bot_api.reply_message(event.reply_token, flex_message)
            except Exception as e_openai:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="ขอโทษเด้อ หมอพืชกำลังงง รบกวนส่งรูปมาใหม่แหน่เด้อ")
                )

    @handler.add(MessageEvent, message=TextMessage)
    def handle_text_message(event):
        if not line_bot_api:
            return
        user_id = event.source.user_id
        user_message = event.message.text
        
        # Correction detection (Natural Feedback)
        # If user says something that sounds like a correction, we log it.
        correction_keywords = ["ไม่ใช่", "บ่แม่น", "เข้าใจผิด", "คือต้น", "มันคือ", "ชื่อจริงคือ", "มันแม่น"]
        is_correction = any(keyword in user_message for keyword in correction_keywords)
        
        if is_correction:
            print(f"Natural Correction detected from {user_id}: {user_message}")
            database.update_feedback(user_id, user_message)
        
        try:
            # Show loading animation for chat as well
            show_loading_animation(user_id)

            history = database.get_recent_chat(user_id)
            last_prediction = database.get_latest_prediction(user_id)
            reply_text = chat_with_bot(
                user_message,
                history=history,
                last_prediction=last_prediction,
            )
            database.save_chat(user_id, "user", user_message)
            database.save_chat(user_id, "assistant", reply_text)

            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=reply_text)
            )
        except Exception as e:
            print(f"Error in chat_with_bot: {e}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="ขอโทษเด้อ หมอพืชกำลังงง รบกวนส่งข้อความมาใหม่แหน่เด้อ")
            )

if __name__ == "__main__":
    port = int(APP_PORT)
    print(f"Starting server on port {port}...")
    app.run(host='0.0.0.0', port=port)
