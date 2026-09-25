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

            # 「開始」ボタンはテキストを持たないアイコンボタン(img alt属性のみ)の可能性が高いため、
            # テキスト一致・img alt一致・aria-label一致を順番に試す。
            clicked = False
            for label in ("入室", "開始", "Join", "参加する", "スタート", "Start"):
                btn = page.query_selector(f'button:has-text("{label}")')
                if btn:
                    btn.click()
                    clicked = True
                    break
            if not clicked:
                for label in ("開始", "入室", "参加", "スタート", "Join", "Start"):
                    btn = page.query_selector(f'button:has(img[alt*="{label}"])')
                    if btn:
                        btn.click()
                        clicked = True
                        break
            if not clicked:
                for label in ("開始", "入室", "参加", "スタート", "Join", "Start"):
                    btn = page.query_selector(f'[aria-label*="{label}"]')
                    if btn:
                        btn.click()
                        clicked = True
                        break

            # 固定3秒待ちではなく、参加者タイル(.peer-view)が出現するまで待つ（最大10秒）
            # BIZMEEはP2P(ブラウザ同士が直接つながるWebRTC)方式のため、
            # 実際に他の参加者と接続が確立するまで増えない可能性がある。
            try:
                page.wait_for_selector(".peer-view", timeout=10000)
            except Exception:
                pass
            page.wait_for_timeout(3000)  # WebRTC(P2P)接続が安定するまでの猶予

            # 実際のDOM構造(ユーザー提供のキャプチャより判明):
            #   .peers > .peer-view (参加者タイル、自分は .peer-view.self) > .footer(表示名)
            # 自分(bot自身)のタイルは除外し、他の参加者のみを数える。
            names = []
            for el in page.query_selector_all(".peer-view"):
                classes = (el.get_attribute("class") or "").split()
                if "self" in classes:
                    continue  # bot自身のタイルは除外
                footer = el.query_selector(".footer")
                text = footer.inner_text().strip() if footer else ""
                if text:
                    names.append(text)

            all_peer_views = page.query_selector_all(".peer-view")
            count = max(0, len(all_peer_views) - 1)  # 自分の分を1引く

            result = {"room": room_name, "count": count, "names": names, "join_button_clicked": clicked}

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
