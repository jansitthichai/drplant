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
from gemini_service import analyze_image as analyze_image_gemini
from openai_service import analyze_image_openai
from line_service import create_flex_message

load_dotenv()

app = Flask(__name__, template_folder='.')

# LINE API Setup
APP_PORT = os.getenv('PORT', default=5000)
CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
CHANNEL_SECRET = os.getenv('LINE_CHANNEL_SECRET')

if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    print('Error: LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET is not set in .env')
    sys.exit(1)

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


@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers.get('X-Line-Signature')

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # Start a new thread for handling the webhook
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

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    message_id = event.message.id
    message_content = line_bot_api.get_message_content(message_id)
    
    # Read image content into memory
    image_data = BytesIO(message_content.content)
    
    # Send to Gemini
    analysis_result = ""
    try:
        # Show loading animation
        show_loading_animation(event.source.user_id)
        
        # Try Gemini First
        analysis_result = analyze_image_gemini(image_data)

        # Check for explicit error strings from Gemini service
        if "Error" in analysis_result and ("429" in analysis_result or "404" in analysis_result or "Resource Exhausted" in analysis_result):
            print(f"Gemini Error ({analysis_result}). Switching to OpenAI...")
            analysis_result = analyze_image_openai(image_data)
        
        # Create Flex Message
        flex_message = create_flex_message(analysis_result)
        
        line_bot_api.reply_message(
            event.reply_token,
            flex_message
        )
    except Exception as e:
        print(f"Error processing image with Gemini: {e}")
        try:
             # Fallback to OpenAI if Gemini throws an unhandled exception
            print("Exception in Gemini. Switching to OpenAI...")
            analysis_result = analyze_image_openai(image_data)
            
            flex_message = create_flex_message(analysis_result)
            line_bot_api.reply_message(event.reply_token, flex_message)
            
        except Exception as e_openai:
            print(f"Error processing image with OpenAI: {e_openai}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="ขอโทษเด้อ หมอพืชกำลังงง รบกวนส่งรูปมาใหม่แหน่เด้อ (Error processing image)")
            )

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="ส่งรูปพืชที่เป็นโรคมาให้หมอเบิ่งแนเด้อ หมอสิซอยวิเคราะห์ให้ (Please send an image of the plant)")
    )

if __name__ == "__main__":
    app.run(port=int(APP_PORT))
