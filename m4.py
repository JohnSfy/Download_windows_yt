import yt_dlp
import os

playlist_url = "https://www.youtube.com/playlist?list=PLG49S3nxzAnl4QDVqK-hOnoqcSKEIDDuv"
output_folder = "downloads"

os.makedirs(output_folder, exist_ok=True)

ydl_opts = {
    'cookiefile': 'cookies.txt',  # export this from your browser
    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
    'merge_output_format': 'mp4',
    'outtmpl': f'{output_folder}/%(playlist_index)03d - %(title).100s.%(ext)s',
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/91.0 Safari/537.36',
    'ignoreerrors': True,
    'no_warnings': True,
    'noplaylist': False,
    'sleep_interval': 2,
    'max_sleep_interval': 5,
    'concurrent_fragment_downloads': 3
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    ydl.download([playlist_url])
