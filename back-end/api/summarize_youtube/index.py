from flask import Flask, request, jsonify
from flask_cors import CORS
from youtube_transcript_api import YouTubeTranscriptApi
from transformers import pipeline
import re
import os
import gc

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "https://video-summarizer-iota.vercel.app"}})
print("CORS enabled for https://video-summarizer-iota.vercel.app")

@app.route('/api/summarize_youtube', methods=['GET'])
def debug_get():
    print("⚠️  Received unexpected GET request to /api/summarize_youtube")
    print(f"🔍 Method: {request.method}")
    print(f"🌐 Remote IP: {request.remote_addr}")
    print(f"🧾 Headers: {dict(request.headers)}")
    print(f"🔗 Full URL: {request.url}")
    print(f"📱 User-Agent: {request.headers.get('User-Agent')}")
    print(f"🪪 Referer: {request.headers.get('Referer')}")
    print(f"🔐 Origin: {request.headers.get('Origin')}")
    
    return jsonify({"error": "Only POST allowed"}), 405

def get_video_id_from_url(url):
    video_id_match = re.search(r'(?:v=|\/)([0-9A-Za-z_-]{11})', url)
    return video_id_match.group(1) if video_id_match else None

@app.route("/")
def home():
    return "Flask YouTube summarizer is running!"

@app.route('/api/summarize_youtube', methods=['POST'], strict_slashes=False)
def summary_api():
    data = request.get_json()
    print("📩 Incoming request:", data)
    url = data.get('url', '')

    video_id = get_video_id_from_url(url)
    if not video_id:
        return jsonify({'error': 'Invalid YouTube URL'}), 400

    try:
        transcript = get_transcript(video_id)
        summary = get_summary(transcript)
        return jsonify({'summary': summary}), 200
    except Exception as e:
        print("🔥 ERROR:", str(e))
        return jsonify({'error': str(e)}), 500

def get_transcript(video_id):
    transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
    transcript = ' '.join([d['text'] for d in transcript_list])
    return transcript

def get_summary(text, max_chunk_size=800):
    # Lazy load summarizer here to reduce memory footprint during cold start
    summariser = pipeline("summarization", model="sshleifer/distilbart-cnn-12-6")

    # Split text into sentence-based chunks
    sentences = re.split(r'(?<=[.?!])\s+', text)
    chunks = []
    current_chunk = ""

    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_chunk_size:
            current_chunk += sentence + " "
        else:
            chunks.append(current_chunk.strip())
            current_chunk = sentence + " "
    if current_chunk:
        chunks.append(current_chunk.strip())

    summaries = []
    for chunk in chunks:
        try:
            result = summariser(chunk, max_length=150, min_length=40, do_sample=False)
            summaries.append(result[0]['summary_text'])
        except Exception as e:
            print(f"🧨 Summarization error on chunk: {e}")
            continue

    # Clear memory after processing
    del summariser
    gc.collect()

    return " ".join(summaries)

# For Railway
application = app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
