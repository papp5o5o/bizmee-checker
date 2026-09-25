import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from playwright.sync_api import sync_playwright

app = Flask(__name__)
CORS(app)

@app.route('/check-room', methods=['POST'])
def check_room():
    data = request.get_json() or {}
    room_name = data.get('room_name')
    if not room_name:
        return jsonify({'error': '部屋名を入力してください'}), 400

    url = f"https://bizmee.net/{room_name}"
    
    try:
        with sync_playwright() as p:
            # カメラ・マイクのアクセスを自動許可し、画面なしでブラウザを起動
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                    "--no-sandbox",
                    "--disable-setuid-sandbox"
                ]
            )
            context = browser.new_context(permissions=['camera', 'microphone'])
            page = context.new_page()
            
            page.goto(url, timeout=30000)
            
            # 開始/入室ボタンがあれば押す
            start_button = page.query_selector('button:has-text("入室")') or page.query_selector('button:has-text("開始")') or page.query_selector('button')
            if start_button:
                start_button.click()
            
            # 画面の読み込み待ち（3秒）
            page.wait_for_timeout(3000)
            
            # 参加者名の取得
            elements = page.query_selector_all('.user-name, .participant-name, video')
            names = []
            for el in elements:
                text = el.inner_text().strip()
                if text and text not in names:
                    names.append(text)
            
            count = len(names) if names else len(elements)
            
            browser.close()
            
            return jsonify({
                'room': room_name,
                'count': count,
                'names': names
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)