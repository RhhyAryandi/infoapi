from flask import Flask, request, jsonify
import asyncio
import aiohttp
import requests
import json
import binascii
import logging
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from google.protobuf.json_format import MessageToJson
from google.protobuf.message import DecodeError
import like_pb2
import like_count_pb2
import uid_generator_pb2

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# ======================================
# 🔹 Load Tokens
# ======================================
def load_tokens():
    try:
        with open("token_bd.json", "r") as f:
            return json.load(f)
    except Exception as e:
        app.logger.error(f"Failed to load tokens: {e}")
        return None

# ======================================
# 🔹 AES Encryptor
# ======================================
def encrypt_message(plaintext: bytes):
    try:
        key = b'Yg&tc%DEuh6%Zc^8'
        iv = b'6oyZDr22E3ychjM%'
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = pad(plaintext, AES.block_size)
        encrypted = cipher.encrypt(padded)
        return binascii.hexlify(encrypted).decode()
    except Exception as e:
        app.logger.error(f"Encryption error: {e}")
        return None

# ======================================
# 🔹 Protobuf Builder
# ======================================
def create_uid_proto(uid):
    try:
        msg = uid_generator_pb2.uid_generator()
        msg.saturn_ = int(uid)
        msg.garena = 1
        return msg.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating UID proto: {e}")
        return None

def create_like_proto(uid, region="bd"):
    try:
        msg = like_pb2.like()
        msg.uid = int(uid)
        msg.region = region
        return msg.SerializeToString()
    except Exception as e:
        app.logger.error(f"Error creating like proto: {e}")
        return None

# ======================================
# 🔹 Encrypt UID
# ======================================
def enc(uid):
    data = create_uid_proto(uid)
    if not data:
        return None
    return encrypt_message(data)

# ======================================
# 🔹 Decode Protobuf
# ======================================
def decode_protobuf(binary):
    try:
        obj = like_count_pb2.Info()
        obj.ParseFromString(binary)
        return obj
    except DecodeError:
        return None
    except Exception as e:
        app.logger.error(f"Decode error: {e}")
        return None

# ======================================
# 🔹 Fetch Player Info (via infoapi)
# ======================================
def fetch_player_info(uid):
    try:
        url = f"https://infoapi-76742.vercel.app/info?server-name=bd&uid={uid}"
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            data = r.json()
            acc = data.get("AccountInfo", {})
            return {
                "UID": acc.get("AccountName", uid),
                "Name": acc.get("AccountName", "Unknown"),
                "Region": acc.get("AccountRegion", "BD"),
                "Likes": acc.get("AccountLikes", 0),
                "Level": acc.get("AccountLevel", 0)
            }
        else:
            app.logger.error(f"infoapi failed {r.status_code}")
            return None
    except Exception as e:
        app.logger.error(f"fetch_player_info error: {e}")
        return None

# ======================================
# 🔹 Request Like (Async)
# ======================================
async def send_request(encrypted_uid, token):
    try:
        url = "https://clientbp.ggblueshark.com/LikeProfile"
        headers = {
            'Authorization': f'Bearer {token}',
            'User-Agent': 'Dalvik/2.1.0 (Linux; Android 9)',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=bytes.fromhex(encrypted_uid), headers=headers) as resp:
                return resp.status
    except Exception as e:
        app.logger.error(f"send_request error: {e}")
        return None

# ======================================
# 🔹 Multiple Like Requests
# ======================================
async def send_multiple_likes(uid):
    tokens = load_tokens()
    if not tokens:
        return "No tokens"
    like_data = create_like_proto(uid)
    encrypted = encrypt_message(like_data)
    if not encrypted:
        return "Encryption failed"
    tasks = []
    for i in range(100):
        token = tokens[i % len(tokens)].get("token")
        tasks.append(send_request(encrypted, token))
    results = await asyncio.gather(*tasks)
    return results

# ======================================
# 🔹 Main /like Endpoint
# ======================================
@app.route('/like', methods=['GET'])
def like_api():
    uid = request.args.get("uid")
    if not uid:
        return jsonify({"error": "UID is required"}), 400

    player = fetch_player_info(uid)
    if not player:
        return jsonify({"error": "Failed to fetch player info"}), 500

    before_likes = player["Likes"]
    name = player["Name"]
    region = player["Region"]
    level = player["Level"]

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(send_multiple_likes(uid))
    loop.close()

    after = fetch_player_info(uid)
    after_likes = after["Likes"] if after else before_likes
    gained = after_likes - before_likes
    status = 1 if gained > 0 else 2

    result = {
        "PlayerNickname": name,
        "UID": uid,
        "Region": region,
        "Level": level,
        "LikesBefore": before_likes,
        "LikesAfter": after_likes,
        "LikesAdded": gained,
        "status": status
    }
    return jsonify(result)

# ======================================
# Flask export (for Vercel)
# ======================================
if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
