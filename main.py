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

            # 「参加する」ボタンを押して入室する
            # （実際のBizmeeの待機画面では「入室」「開始」というテキストは存在せず、
            #   「参加する」というテキストのボタンのみが入室ボタン。
            #   待機画面にはマイクオフ・カメラオフの切替ボタンが先に存在するため、
            #   むやみに最初の<button>を押すと入室できない）
            #
            # SvelteKit製のアプリはgoto()のload完了後もJSでの画面描画(ハイドレーション)が
            # 続いているため、即座にquery_selectorすると見つからないことがある。
            # そのため明示的にボタンが描画されるまで待つ。
            try:
                page.wait_for_selector('button:has-text("参加する")', timeout=15000)
            except Exception:
                pass  # 見つからなければ下のquery_selectorでNoneになり、デバッグ情報を返す

            start_button = page.query_selector('button:has-text("参加する")')
            if start_button:
                start_button.click()
            else:
                # デバッグ用に、実際に描画された画面のタイトルとbody先頭部分を返す
                page_title = page.title()
                body_html = page.eval_on_selector('body', 'el => el.innerHTML') if page.query_selector('body') else ''
                browser.close()
                return jsonify({
                    'error': '参加ボタンが見つかりませんでした（部屋が存在しないか、画面構成が変更されています）',
                    'debug_title': page_title,
                    'debug_body_snippet': body_html[:1500]
                }), 404

            # 入室後、他参加者との接続・描画待ち
            page.wait_for_timeout(5000)

            # 参加者一覧の取得
            # 実際の入室後画面では、参加者1人につき .peer-view 要素が1つ生成され、
            # その中の .footer 要素に表示名が入る（.user-name / .participant-name は存在しない）。
            # 自分自身の映像プレビューにも class="peer-view self ..." が付くため、
            # 「他の参加者」だけを数えるには self を除外する必要がある。
            peer_views = page.query_selector_all('.peer-view')

            names = []
            other_count = 0
            for peer in peer_views:
                class_attr = peer.get_attribute('class') or ''
                is_self = 'self' in class_attr.split()

                footer = peer.query_selector('.footer')
                text = footer.inner_text().strip() if footer else ''

                if not is_self:
                    other_count += 1
                    if text:
                        names.append(text)

            browser.close()

            return jsonify({
                'room': room_name,
                'count': other_count,
                'names': names,
                'debug_total_peer_views': len(peer_views)  # 自分自身を含む総数（確認用）
            })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
    
