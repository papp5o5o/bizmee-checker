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
            page.wait_for_timeout(2000)
            
            # 入室ボタンのクリック処理
            buttons = page.query_selector_all('button, a, input[type="button"]')
            for btn in buttons:
                text = btn.inner_text().strip()
                if any(keyword in text for keyword in ['入室', '開始', 'Enter', 'Join']):
                    try:
                        btn.click()
                    except:
                        pass
                    break
            
            # 入室後の読み込み待ち
            page.wait_for_timeout(4000)
            
            # 画面上のすべてのビデオ（映像枠）を取得
            videos = page.query_selector_all('video')
            total_videos = len(videos)
            
            # 調査プログラム自身（1枠分）を除外した人数を計算
            other_count = max(0, total_videos - 1)
            
            # 画面内のテキスト要素から名前と思われる文字列を取得
            names = []
            labels = page.query_selector_all('.name, .user-name, .participant, [class*="name"]')
            for lbl in labels:
                txt = lbl.inner_text().strip()
                if txt and txt not in names and len(txt) < 30:
                    names.append(txt)
            
            browser.close()
            
            return jsonify({
                'room': room_name,
                'count': len(names) if names else other_count,
                'names': names
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
