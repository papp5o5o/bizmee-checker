import base64
import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from playwright.sync_api import sync_playwright

app = Flask(__name__)
CORS(app)


def scrape_room(room_name, debug=False):
    url = f"https://bizmee.net/{room_name}"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",  # コンテナの/dev/shmが小さく、Chromiumが原因不明にクラッシュするのを防ぐ
                "--disable-gpu",
                "--disable-extensions",
                "--disable-background-networking",
                "--single-process",  # メモリ使用量を削る（不安定なら外す）
            ],
        )
        try:
            context = browser.new_context(permissions=["camera", "microphone"])
            page = context.new_page()

            console_logs = []
            page_errors = []
            page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
            page.on("pageerror", lambda err: page_errors.append(str(err)))

            page.goto(url, timeout=30000)
            page.wait_for_timeout(1500)  # 入室前ロビー画面の描画待ち

            before_join_html = page.content() if debug else None
            before_join_shot = page.screenshot(full_page=True) if debug else None

            # 入室/開始ボタンがあれば押す（文言のゆれに対応）
            for label in ("入室", "開始", "Join", "参加する"):
                btn = page.query_selector(f'button:has-text("{label}")')
                if btn:
                    btn.click()
                    break

            # 固定3秒待ちではなく、video要素が出現するまで待つ（最大10秒）
            # BIZMEEはP2P(ブラウザ同士が直接つながるWebRTC)方式のため、
            # 実際に他の参加者と接続が確立するまでvideo要素が増えない可能性がある。
            try:
                page.wait_for_selector("video", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(3000)  # WebRTC(P2P)接続が安定するまでの猶予

            # 名前は video タグの中には入っていない（video要素はテキストを持たない）ので、
            # 名前表示用と思われる要素を別途探す。クラス名は推測なので複数パターンを試す。
            names = []
            for el in page.query_selector_all(
                ".user-name, .participant-name, [class*='name'], [class*='Name']"
            ):
                text = el.inner_text().strip()
                if text and text not in names:
                    names.append(text)

            video_count = len(page.query_selector_all("video"))
            count = len(names) if names else video_count

            result = {"room": room_name, "count": count, "names": names}

            if debug:
                # 実際に取得できたHTML・スクリーンショット・consoleログを返す。
                # ここから本物のクラス名/構造や、WebRTC接続が失敗していないかを確認する。
                result["before_join_html"] = before_join_html
                result["before_join_screenshot_base64"] = base64.b64encode(before_join_shot).decode()
                result["after_join_html"] = page.content()
                result["after_join_screenshot_base64"] = base64.b64encode(
                    page.screenshot(full_page=True)
                ).decode()
                result["console_logs"] = console_logs[-50:]
                result["page_errors"] = page_errors

            return result
        finally:
            # 例外が起きてもブラウザプロセスを必ず閉じる。
            # ここが無いと、失敗するたびにChromiumプロセスが残り続け、
            # メモリ制限の厳しいRenderの無料枠では数回の失敗でメモリを食い潰して
            # 以降のリクエストが「エラーも出ずに固まる」状態になり得る。
            browser.close()


@app.route("/", methods=["GET"])
def health_check():
    # ブラウザで直接開いて動作確認できる簡易ヘルスチェック
    return jsonify({"status": "ok"})


@app.route("/check-room", methods=["POST"])
def check_room():
    data = request.get_json() or {}
    room_name = data.get("room_name")
    if not room_name:
        return jsonify({"error": "部屋名を入力してください"}), 400
    try:
        return jsonify(scrape_room(room_name))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/debug-room", methods=["POST"])
def debug_room():
    """調査用エンドポイント。実際に取得できたHTMLとconsoleログをそのまま返す。
    正しいセレクタが分かるまでの間、一時的にこれを叩いて確認する用途。"""
    data = request.get_json() or {}
    room_name = data.get("room_name")
    if not room_name:
        return jsonify({"error": "部屋名を入力してください"}), 400
    try:
        return jsonify(scrape_room(room_name, debug=True))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
