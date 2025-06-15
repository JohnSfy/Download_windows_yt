from flask import Flask, request, jsonify, send_from_directory, send_file, Blueprint
import yt_dlp
import os
import re
import uuid
from datetime import timedelta
from mutagen.mp3 import MP3

app = Flask(__name__)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
download_progress = {}

bp = Blueprint("ytmp3", __name__, url_prefix="/downloadmp3")

def sanitize_url(url):
    return re.sub(r"[&?]t=\d+s", "", url)


@bp.route("/")
def index():
    return send_file("index.html")


@bp.route("/convert", methods=["POST"])
def convert():
    data = request.get_json()
    url = sanitize_url(data.get("url", ""))
    quality = data.get("quality", "mpeg")

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    job_id = str(uuid.uuid4())
    progress = {}

    def progress_hook(d):
        progress["status"] = d.get("status")
        progress["downloaded"] = d.get("downloaded_bytes", 0)
        progress["total"] = d.get("total_bytes", d.get("total_bytes_estimate", 0))
        download_progress[job_id] = progress

    try:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320" if quality == "pantas" else "192",
            }],
            "progress_hooks": [progress_hook],
            "extractor_args": {
                "youtube": {
                    "player_client": ["android"],
                    "player_skip": ["webpage", "configs"],
                }
            },
            "nocheckcertificate": True,
            "ignoreerrors": True,
            "no_warnings": True,
            "quiet": True,
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Sec-Fetch-Mode": "navigate",
            }
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(result).rsplit(".", 1)[0] + ".mp3"

            return jsonify({
                "title": result.get("title", ""),
                "filename": os.path.basename(filename),
                "job_id": job_id
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/download/<path:filename>")
def download_file(filename):
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


@bp.route("/library")
def library():
    files = [
        f for f in os.listdir(DOWNLOAD_DIR)
        if f.lower().endswith(".mp3")
    ]
    
    file_info = []
    for file in files:
        path = os.path.join(DOWNLOAD_DIR, file)
        try:
            audio = MP3(path)
            duration = str(timedelta(seconds=int(audio.info.length)))
            size_mb = round(os.path.getsize(path) / (1024 * 1024), 2)
            bitrate = int(audio.info.bitrate / 1000)

            file_info.append({
                "filename": file,
                "duration": duration,
                "size_mb": size_mb,
                "bitrate": f"{bitrate} kbps"
            })
        except Exception as e:
            print(f"[ERROR] Failed to read metadata for {file}: {e}")
            file_info.append({
                "filename": file,
                "duration": "Unknown",
                "size_mb": "?",
                "bitrate": "Unknown"
            })


    return jsonify(file_info)


@bp.route("/delete/<path:filename>", methods=["DELETE"])
def delete_file(filename):
    filepath = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(filepath):
        os.remove(filepath)
        return jsonify({"message": f"{filename} deleted"}), 200
    return jsonify({"error": "File not found"}), 404


@bp.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory('images', filename)

# Register the blueprint here
app.register_blueprint(bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
