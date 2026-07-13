import os
import requests
from flask import Flask, request, jsonify
import google.generativeai as genai

app = Flask(__name__)

# ==================== الإعدادات (تُقرأ من متغيرات البيئة) ====================
PAGE_ACCESS_TOKEN = os.environ.get("PAGE_ACCESS_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "ahl_verify_2026")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "0924565333")
PHONE_NUMBER = os.environ.get("PHONE_NUMBER", "0914565333")
MAPS_LINK = os.environ.get("MAPS_LINK", "https://maps.app.goo.gl/ToM2QKXZ9W64hadU9")
STORE_ADDRESS = os.environ.get("STORE_ADDRESS", "شارع الكماليات، بالقرب من جامعة ناصر")
STORE_HOURS = os.environ.get("STORE_HOURS", "يومياً من الساعة 9 صباحاً حتى صلاة المغرب")
STORE_NAME = os.environ.get("STORE_NAME", "شركة الحلول الجديدة لاستيراد وبيع كماليات السيارات")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-2.0-flash"

# ==================== حالة المستخدم (في الذاكرة) ====================
# لكل زبون (PSID) نحفظ آخر مرحلة وصل لها بالمحادثة
SESSIONS = {}

FB_API_URL = "https://graph.facebook.com/v20.0/me/messages"


# ==================== دوال إرسال الرسائل لفيسبوك ====================
def send_message(psid, message_payload):
    if not PAGE_ACCESS_TOKEN:
        print("PAGE_ACCESS_TOKEN غير موجود")
        return
    params = {"access_token": PAGE_ACCESS_TOKEN}
    headers = {"Content-Type": "application/json"}
    data = {"recipient": {"id": psid}, "message": message_payload}
    resp = requests.post(FB_API_URL, params=params, headers=headers, json=data)
    if resp.status_code != 200:
        print("خطأ بالإرسال:", resp.text)


def send_text(psid, text):
    send_message(psid, {"text": text})


def send_quick_replies(psid, text, options):
    """options: قائمة من (title, payload)"""
    quick_replies = [
        {"content_type": "text", "title": title, "payload": payload}
        for title, payload in options
    ]
    send_message(psid, {"text": text, "quick_replies": quick_replies})


# ==================== الرسائل الجاهزة ====================
def msg_welcome():
    return f"أهلاً بك في {STORE_NAME} 🚗\nهل طلبك بالجملة أم قطعة واحدة؟"


def msg_retail():
    return "نعتذر، البيع بالتجزئة غير متوفر حالياً، نتعامل بالجملة فقط 🙏"


def msg_ask_delivery():
    return "تمام، هل تحتاج التوصيل أم ستأتي إلى المحل؟"


def msg_delivery():
    return (
        "يمكنك إرسال المنتجات التي تريدها وسيتم الرد عليك عبر:\n"
        f"📱 واتساب: {WHATSAPP_NUMBER}\n"
        f"☎️ هاتف: {PHONE_NUMBER}"
    )


def msg_pickup():
    return (
        f"📍 موقعنا: {STORE_ADDRESS}\n"
        f"🗺️ الخريطة: {MAPS_LINK}\n"
        f"🕘 أوقات الدوام: {STORE_HOURS}"
    )


def msg_contact_footer():
    return (
        f"\n\nللاطلاع على المتوفر فعلياً والأسعار تواصل معنا مباشرة:\n"
        f"📱 واتساب: {WHATSAPP_NUMBER} | ☎️ {PHONE_NUMBER}\n"
        f"🗺️ {MAPS_LINK}"
    )


# ==================== الذكاء الاصطناعي (للأسئلة الحرة) ====================
SYSTEM_PROMPT = f"""أنت مساعد رد آلي لصفحة فيسبوك تابعة لـ "{STORE_NAME}"،
شركة تستورد وتبيع كماليات وإضاءة السيارات بالجملة فقط (لا تبيع بالتجزئة).

قواعد صارمة يجب اتباعها دائماً:
- لا تؤكد أبداً أن منتجاً معيناً متوفر أو غير متوفر لديهم بالمخزون، لأنك لا تملك بيانات المخزون الفعلية.
- أعطِ معلومة عامة مفيدة وموجزة (فكرة عن نوع المنتج، استخداماته، الفروقات بين الأنواع) دون الجزم بالتوفر.
- كن مختصراً جداً (2-3 جمل كحد أقصى).
- تكلم بالعربية بأسلوب ودود واحترافي.
- لا تذكر أي أسعار أبداً.
"""


def ask_gemini(user_text):
    if not GEMINI_API_KEY:
        return "شكراً لتواصلك معنا! سيتم الرد عليك من فريقنا قريباً."
    try:
        model = genai.GenerativeModel(GEMINI_MODEL, system_instruction=SYSTEM_PROMPT)
        response = model.generate_content(user_text)
        return response.text.strip()
    except Exception as e:
        print("خطأ بـ Gemini:", e)
        return "شكراً لسؤالك! تواصل معنا مباشرة للمزيد من التفاصيل."


# ==================== منطق المحادثة ====================
def handle_payload(psid, payload):
    if payload == "GET_STARTED" or payload == "START_OVER":
        SESSIONS[psid] = {"stage": "ask_type"}
        send_quick_replies(psid, msg_welcome(), [("🏢 جملة", "TYPE_WHOLESALE"), ("👤 قطعة", "TYPE_RETAIL")])

    elif payload == "TYPE_RETAIL":
        send_text(psid, msg_retail())
        SESSIONS.pop(psid, None)

    elif payload == "TYPE_WHOLESALE":
        SESSIONS[psid] = {"stage": "ask_delivery"}
        send_quick_replies(psid, msg_ask_delivery(), [("🚚 توصيل", "MODE_DELIVERY"), ("🏬 سآتي للمحل", "MODE_PICKUP")])

    elif payload == "MODE_DELIVERY":
        send_text(psid, msg_delivery())
        SESSIONS.pop(psid, None)

    elif payload == "MODE_PICKUP":
        send_text(psid, msg_pickup())
        SESSIONS.pop(psid, None)

    else:
        handle_payload(psid, "GET_STARTED")


def handle_free_text(psid, text):
    session = SESSIONS.get(psid, {})
    stage = session.get("stage")

    # لو المستخدم بمنتصف الفلو وكتب نص حر بدل ما يضغط زر، نعيد له نفس الخيارات
    if stage == "ask_type":
        send_quick_replies(psid, "من فضلك اختر أحد الخيارين:", [("🏢 جملة", "TYPE_WHOLESALE"), ("👤 قطعة", "TYPE_RETAIL")])
        return
    if stage == "ask_delivery":
        send_quick_replies(psid, "من فضلك اختر أحد الخيارين:", [("🚚 توصيل", "MODE_DELIVERY"), ("🏬 سآتي للمحل", "MODE_PICKUP")])
        return

    # ما فيه محادثة نشطة -> نستخدم الذكاء الاصطناعي للرد، ثم نوجهه لبداية الفلو
    ai_reply = ask_gemini(text)
    send_text(psid, ai_reply + msg_contact_footer())
    send_quick_replies(psid, "هل طلبك بالجملة أم قطعة واحدة؟", [("🏢 جملة", "TYPE_WHOLESALE"), ("👤 قطعة", "TYPE_RETAIL")])
    SESSIONS[psid] = {"stage": "ask_type"}


# ==================== مسارات فلاسك ====================
@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        return challenge, 200
    return "Verification failed", 403


@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if data.get("object") != "page":
        return jsonify(status="ignored"), 200

    for entry in data.get("entry", []):
        for event in entry.get("messaging", []):
            psid = event["sender"]["id"]

            if "postback" in event:
                payload = event["postback"].get("payload", "GET_STARTED")
                handle_payload(psid, payload)

            elif "message" in event:
                message = event["message"]
                if message.get("is_echo"):
                    continue
                if "quick_reply" in message:
                    handle_payload(psid, message["quick_reply"]["payload"])
                elif "text" in message:
                    handle_free_text(psid, message["text"])

    return jsonify(status="ok"), 200


@app.route("/", methods=["GET"])
def health():
    return "Bot is running", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
