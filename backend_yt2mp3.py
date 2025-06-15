from flask import Flask, request, jsonify, send_from_directory, send_file, Blueprint, Response
import yt_dlp
import os
import re
import uuid
from datetime import timedelta
from mutagen.mp3 import MP3
import io
import tempfile
import urllib.parse
import subprocess
import shutil
import json
from datetime import datetime

app = Flask(__name__)
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
download_progress = {}

bp = Blueprint("ytmp3", __name__, url_prefix="/downloadmp3")

def sanitize_url(url):
    return re.sub(r"[&?]t=\d+s", "", url)

def sanitize_filename(filename):
    """Sanitize filename to be safe for all operating systems while preserving Greek characters."""
    # Remove any null bytes
    filename = filename.replace('\0', '')
    
    # Replace invalid characters with underscores
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')
    
    # Ensure the filename is not too long (Windows has a 255 character limit)
    if len(filename) > 240:  # Leave room for extension
        filename = filename[:240]
    
    return filename

def get_ffmpeg_paths():
    """Get the paths to ffmpeg and ffprobe executables."""
    # First check if ffmpeg is in the system PATH
    try:
        ffmpeg_path = subprocess.check_output(['where', 'ffmpeg'], stderr=subprocess.STDOUT).decode().strip().split('\n')[0]
        ffprobe_path = subprocess.check_output(['where', 'ffprobe'], stderr=subprocess.STDOUT).decode().strip().split('\n')[0]
        return {"ffmpeg": ffmpeg_path, "ffprobe": ffprobe_path}
    except subprocess.CalledProcessError:
        # If not in PATH, check common installation locations
        common_paths = [
            os.path.join(os.getcwd(), "ffmpeg", "bin"),
            os.path.join(os.getcwd(), "ffmpeg"),
            os.path.join(os.path.expanduser("~"), "ffmpeg", "bin"),
            os.path.join(os.path.expanduser("~"), "ffmpeg"),
            "C:\\ffmpeg\\bin",
            "C:\\Program Files\\ffmpeg\\bin",
            "C:\\Program Files (x86)\\ffmpeg\\bin"
        ]
        
        for path in common_paths:
            ffmpeg_exe = os.path.join(path, "ffmpeg.exe")
            ffprobe_exe = os.path.join(path, "ffprobe.exe")
            if os.path.exists(ffmpeg_exe) and os.path.exists(ffprobe_exe):
                return {"ffmpeg": ffmpeg_exe, "ffprobe": ffprobe_exe}
        
        # If still not found, return None for both paths
        return {"ffmpeg": None, "ffprobe": None}

def check_ffmpeg():
    ffmpeg_path = get_ffmpeg_paths()["ffmpeg"]
    ffprobe_path = get_ffmpeg_paths()["ffprobe"]
    
    if not ffmpeg_path:
        return False, "FFmpeg not found in PATH or common locations"
    
    if not ffprobe_path:
        return False, "FFprobe not found in PATH or common locations"
    
    try:
        result = subprocess.run([ffmpeg_path, '-version'], capture_output=True, text=True, check=True)
        return True, {"ffmpeg": ffmpeg_path, "ffprobe": ffprobe_path}
    except Exception as e:
        return False, str(e)

@bp.route("/")
def index():
    return send_file("index.html")

@bp.route("/convert", methods=["POST"])
def convert():
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({"error": "No URL provided"}), 400
            
        url = data['url']
        quality = data.get('quality', 'pantas')  # Default to 'pantas' if not specified
        
        # Create temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create temporary file paths
            temp_audio = os.path.join(temp_dir, 'audio.m4a')
            temp_mp3 = os.path.join(temp_dir, 'audio.mp3')
            
            # Get FFmpeg paths
            ffmpeg_paths = get_ffmpeg_paths()
            if not all(ffmpeg_paths.values()):
                return jsonify({"error": "FFmpeg not found"}), 500
                
            ydl_opts = {
                "format": "bestaudio[ext=m4a]/bestaudio/best",
                "outtmpl": temp_audio,
                "postprocessors": [],  # Remove the FFmpegExtractAudio postprocessor
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
                },
                "ffmpeg_location": ffmpeg_paths["ffmpeg"],
                "ffprobe_location": ffmpeg_paths["ffprobe"],
                "prefer_ffmpeg": True,
                "verbose": True,
                "progress_hooks": [lambda d: print(f"Download progress: {d.get('status', 'unknown')}")],
                "merge_output_format": "m4a"
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    # First try to extract info without downloading
                    print("Extracting video information...")
                    info = ydl.extract_info(url, download=False)
                    if info is None:
                        return jsonify({"error": "Could not extract video information"}), 400
                    
                    # Get video title and sanitize it
                    video_title = info.get('title', 'video')
                    safe_title = sanitize_filename(video_title)
                    print(f"Original title: {video_title}")
                    print(f"Sanitized title: {safe_title}")
                    
                    # Store the video info in the library
                    video_id = info.get('id', '')
                    if video_id:
                        library_path = os.path.join(os.getcwd(), 'library.json')
                        library = {}
                        if os.path.exists(library_path):
                            try:
                                with open(library_path, 'r', encoding='utf-8') as f:
                                    library = json.load(f)
                            except json.JSONDecodeError:
                                library = {}
                        
                        library[video_id] = {
                            'title': video_title,
                            'url': url,
                            'date_added': datetime.now().isoformat()
                        }
                        
                        with open(library_path, 'w', encoding='utf-8') as f:
                            json.dump(library, f, ensure_ascii=False, indent=2)
                    
                    print(f"Downloading: {video_title}")
                    
                    # Download the audio
                    try:
                        ydl.download([url])
                    except Exception as download_error:
                        print(f"Download error: {str(download_error)}")
                        return jsonify({"error": f"Download failed: {str(download_error)}"}), 500
                    
                    # Check if the file was created and has content
                    if not os.path.exists(temp_audio):
                        print(f"Audio file not found at: {temp_audio}")
                        return jsonify({"error": "Failed to download audio"}), 500
                    
                    print(f"Audio file downloaded successfully. Size: {os.path.getsize(temp_audio)} bytes")
                    
                    # Convert to MP3 using FFmpeg directly
                    print("Converting to MP3...")
                    ffmpeg_cmd = [
                        ffmpeg_paths["ffmpeg"],
                        "-i", temp_audio,
                        "-vn",  # No video
                        "-ar", "44100",  # Sample rate
                        "-ac", "2",  # Stereo
                        "-b:a", "320k" if quality == "pantas" else "192k",  # Bitrate
                        "-y",  # Overwrite output file
                        temp_mp3
                    ]
                    
                    try:
                        result = subprocess.run(ffmpeg_cmd, check=True, capture_output=True, text=True)
                        print("FFmpeg conversion successful")
                    except subprocess.CalledProcessError as e:
                        print(f"FFmpeg error: {e.stderr}")
                        return jsonify({"error": f"FFmpeg conversion failed: {e.stderr}"}), 500
                    
                    # Clean up the temporary M4A file after successful conversion
                    try:
                        os.remove(temp_audio)
                        print("Cleaned up temporary M4A file")
                    except Exception as e:
                        print(f"Warning: Could not remove temporary file: {str(e)}")
                    
                    if not os.path.exists(temp_mp3):
                        print(f"MP3 file not found at: {temp_mp3}")
                        return jsonify({"error": "Failed to convert to MP3"}), 500
                        
                    file_size = os.path.getsize(temp_mp3)
                    if file_size == 0:
                        print("Generated MP3 file is empty")
                        return jsonify({"error": "Generated MP3 file is empty"}), 500
                        
                    print(f"MP3 file created successfully. Size: {file_size} bytes")
                    
                    # Read the MP3 file
                    with open(temp_mp3, 'rb') as f:
                        mp3_data = f.read()
                    
                    if len(mp3_data) == 0:
                        print("MP3 data is empty after reading")
                        return jsonify({"error": "Generated MP3 file is empty"}), 500
                    
                    # URL encode the filename for the Content-Disposition header
                    # Use UTF-8 encoding for the filename
                    encoded_filename = urllib.parse.quote(safe_title.encode('utf-8'))
                    
                    print("Sending MP3 file to client...")
                    # Create a response with the MP3 data
                    response = Response(
                        mp3_data,
                        mimetype='audio/mpeg',
                        headers={
                            'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}.mp3",
                            'Content-Length': str(len(mp3_data))
                        }
                    )
                    
                    return response
                    
                except Exception as e:
                    print(f"Error during download: {str(e)}")
                    return jsonify({"error": f"Download failed: {str(e)}"}), 500
                    
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

@bp.route('/downloadmp3/library', methods=['GET'])
def get_library():
    try:
        library_path = os.path.join(os.getcwd(), 'library.json')
        if not os.path.exists(library_path):
            return jsonify([])
            
        with open(library_path, 'r', encoding='utf-8') as f:
            library = json.load(f)
            
        # Convert the library to a list of items
        items = []
        for video_id, data in library.items():
            items.append({
                'id': video_id,
                'title': data['title'],
                'url': data['url'],
                'date_added': data['date_added']
            })
            
        # Sort by date added, newest first
        items.sort(key=lambda x: x['date_added'], reverse=True)
        
        return jsonify(items)
    except Exception as e:
        print(f"Error getting library: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Register the blueprint here
app.register_blueprint(bp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
