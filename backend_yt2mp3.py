from flask import Flask, request, jsonify, send_from_directory, send_file, Blueprint, Response
import yt_dlp
import os
import re
import uuid
from datetime import timedelta
from mutagen.mp3 import MP3
import io
import tempfile

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

    try:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as temp_file:
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": temp_file.name,
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "320" if quality == "pantas" else "192",
                }],
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
                try:
                    # First try to extract info without downloading
                    info = ydl.extract_info(url, download=False)
                    if info is None:
                        return jsonify({"error": "Could not extract video information"}), 400
                    
                    # Get video title for the filename
                    video_title = info.get('title', 'video')
                    safe_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
                    
                    # Download and convert to MP3
                    ydl.download([url])
                    
                    # Read the temporary file
                    with open(temp_file.name, 'rb') as f:
                        mp3_data = f.read()
                    
                    # Create a response with the MP3 data
                    response = Response(
                        mp3_data,
                        mimetype='audio/mpeg',
                        headers={
                            'Content-Disposition': f'attachment; filename="{safe_title}.mp3"',
                            'Content-Length': str(len(mp3_data))
                        }
                    )
                    
                    return response
                    
                except Exception as e:
                    print(f"Error during download: {str(e)}")
                    return jsonify({"error": f"Download failed: {str(e)}"}), 500
                finally:
                    # Clean up the temporary file
                    try:
                        os.unlink(temp_file.name)
                    except:
                        pass
                    
    except Exception as e:
        print(f"Error in convert function: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bp.route("/library")
def library():
    return jsonify([])  # Return empty list since we're not storing files anymore


@bp.route("/delete/<path:filename>", methods=["DELETE"])
def delete_file(filename):
    return jsonify({"message": "File system storage is disabled"}), 200


@bp.route('/images/<path:filename>')
def serve_image(filename):
    return send_from_directory('images', filename)

# Register the blueprint here
app.register_blueprint(bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
