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
            
            # 入室用ボタンがあればクリック
            buttons = page.query_selector_all('button')
            for btn in buttons:
                txt = btn.inner_text().strip()
                if any(k in txt for k in ['開始', '入室', '参加', 'Enter', 'Join']):
                    try:
                        btn.click()
                    except:
                        pass
            
            # 参加者エリア（.peers または .peer-view）の描画を待機
            try:
                page.wait_for_selector('.peers, .peer-view', timeout=8000)
            except:
                pass
            
            page.wait_for_timeout(3000)
            
            # 自分以外（.self を持たない .peer-view）を取得
            other_peers = page.query_selector_all('.peer-view:not(.self)')
            
            names = []
            for peer in other_peers:
                # ユーザー名の要素（aタグなど）を探してテキストを抽出
                name_elem = peer.query_selector('a') or peer
                if name_elem:
                    full_text = name_elem.inner_text().strip()
                    if full_text:
                        # 複数行ある場合は最初の1行目を名前として取得
                        first_line = full_text.split('\n')[0].strip()
                        if first_line and first_line not in names:
                            names.append(first_line)
            
            count = len(other_peers)
            
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
