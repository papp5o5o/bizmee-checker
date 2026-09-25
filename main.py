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
            page.wait_for_timeout(3000)
            
            # 1. 名前入力欄があれば「監視Bot」と入力
            name_input = page.query_selector('input[type="text"], input')
            if name_input:
                try:
                    name_input.fill('監視Bot')
                except:
                    pass

            # 2. 入室ボタンを探してクリック
            btn_info = "ボタンが見つかりませんでした"
            start_btn = page.query_selector('button:has-text("入室"), button:has-text("開始"), button:has-text("参加"), button')
            if start_btn:
                btn_info = f"発見したボタン: {start_btn.inner_text().strip()}"
                try:
                    start_btn.click()
                    btn_info += " (クリック成功)"
                except Exception as click_err:
                    btn_info += f" (クリック失敗: {click_err})"
            
            # 3. 通信接続と画面読み込みを待機（6秒）
            page.wait_for_timeout(6000)
            
            # 4. 画面内のピア枠 (.peer-view) の状態を確認
            all_peers = page.query_selector_all('.peer-view')
            other_peers = page.query_selector_all('.peer-view:not(.self)')
            
            names = []
            for peer in other_peers:
                name_elem = peer.query_selector('a') or peer
                if name_elem:
                    txt = name_elem.inner_text().strip()
                    if txt:
                        first_line = txt.split('\n')[0].strip()
                        if first_line and first_line not in names:
                            names.append(first_line)
            
            browser.close()
            
            return jsonify({
                'room': room_name,
                'debug_button': btn_info,
                'total_peers_detected': len(all_peers),
                'count': len(other_peers),
                'names': names
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
